# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import datetime
import logging

from sqlalchemy.exc import IntegrityError

from arbiter.backends import analysis_backends
from arbiter.component import Component
from arbiter.const import JOB_STATUS_NEW
from arbiter.database import DbSession, DbBounty, DbArtifact, DbArtifactVerdict
from arbiter.events import event, dispatch_event, periodic
from arbiter.ipfs import ipfs_json, ipfs_download, IPFSNotFoundError
from arbiter.polyswarm_api import Bounty, PolySwarmError
from arbiter.utils import verdict_show

log = logging.getLogger(__name__)

def bounty_settle_manual(guid, verdicts):
    s = DbSession()
    bounty = s.query(DbBounty).with_for_update().filter_by(guid=guid).first()

    if not bounty:
        s.close()
        raise KeyError("No such bounty")
    elif bounty.truth_settled:
        s.close()
        raise ValueError("Bounty was already settled")

    need = s.query(DbArtifact).filter_by(bounty_id=bounty.id).count()
    if need != len(verdicts):
        s.close()
        raise ValueError("Need %s verdict(s), not %s" % (need, len(verdicts)))

    log.info("Manually set bounty %s verdict to %s", guid, verdicts)
    bounty.truth_value = verdicts
    bounty.truth_manual = True
    s.add(bounty)
    s.commit()
    s.close()

class BountyComponent(Component):
    """Keep track of bounties"""
    def __init__(self, parent):
        self.polyswarm = parent.polyswarm
        self.expires = parent.config.expires
        self.cur_block = None
        self.pending_bounties = set()

    @event("check_settle")
    def check_settle(self):
        if self.cur_block is None:
            return

        s = DbSession()
        bounties = s.query(DbBounty.guid, DbBounty.truth_value) \
            .filter(DbBounty.settle_block <= self.cur_block) \
            .filter_by(truth_settled=False) \
            .filter(DbBounty.truth_value.isnot(None))

        for bounty in bounties.all():
            # Avoid double work; still a bit racy...
            if bounty.guid not in self.pending_bounties:
                log.debug("Pending bounty: %s", bounty.guid)
                self.pending_bounties.add(bounty[0])
                dispatch_event("settle_bounty_attempt", (bounty[0], bounty[1]))

        s.close()

    @event("block")
    def block_updated(self, block_number):
        if self.cur_block is not None and block_number <= self.cur_block:
            return
        #log.debug("Updating block to #%s", block_number)
        self.cur_block = block_number
        dispatch_event("check_settle")

    @event("settle_bounty_attempt", serialize=False)
    def settle_bounty_attempt(self, guid, value):
        result = False
        try:
            log.info("%s | Settle bounty value: %s", guid, verdict_show(value))
            self.polyswarm.settle_bounty(guid, value)
            result = True

        except PolySwarmError as e:
            if e.status == 404:
                # Record permanent failure: TODO: log an error, mark bounty
                log.error("Bounty no longer exists (double submit?)")
                result = True
            else:
                log.exception("API error")
                return
        except:
            log.exception("Failed to settle bounty")
            return
        finally:
            self.pending_bounties.discard(guid)

        if result:
            s = DbSession()
            bounty = s.query(DbBounty).with_for_update() \
                .filter_by(guid=guid).one()
            bounty.truth_settled = True
            s.add(bounty)
            s.commit()
            s.close()

        try:
            assertions = self.polyswarm.bounty_assertions(guid)
            if not assertions:
                log.debug("%s | No assertions", guid)
            for a in assertions:
                mask = fix_bitlist(a["mask"], len(value))
                verdicts = fix_bitlist(a["verdicts"], len(value))
                disagree = False
                show = ""
                for v, m, x in zip(value, mask, verdicts):
                    if m:
                        if v != x:
                            disagree = True
                            show += str(x)[:1]
                        else:
                            show += str(x)[:1].lower()
                    else:
                        show += "."
                if disagree:
                    log.warning("%s | Expert %s disagrees! Their verdict: %s",
                                guid, a["author"], show)
                else:
                    log.debug("%s | Assertion: %s", guid, show)

        except:
            log.exception("Failed to check assertions")

    @event("bounty", serialize=False)
    def bounty_pre(self, bounty):
        """A bounty has become available: download its manifest in parallel."""
        if not bounty["resolved"]:
            try:
                ipfs_download(bounty["uri"])
            except IPFSNotFoundError:
                # Shouldn't happen in production
                return
            except:
                # TODO: track some well-known issues (e.g. disk full, ...)
                # TODO: right now we'll skip these bounties!
                log.warning("Couldn't fetch artifact data for bounty %s",
                            bounty["guid"])
                return
            # TODO: check manifest?
            # TODO: recursively download all artifacts
        dispatch_event("bounty_with_manifest", (bounty,))

    @event("bounty_with_manifest")
    def bounty_with_manifest(self, bounty):
        """A bounty has become available: register it for processing"""
        bounty = Bounty.from_dict(bounty)

        if bounty.resolved:
            # TODO: we can use this to abort pending tasks for this bounty
            return

        # Test:
        # - Expiry

        # {hash, name}, both matter
        manifest = ipfs_json(bounty.uri)["result"]
        if not manifest:
            log.warning("Bounty %s has no artifacts", bounty.guid)
            return

        deadline = datetime.datetime.utcnow() + self.expires

        s = DbSession()
        b = DbBounty(guid=bounty.guid,
                     expires=deadline,
                     settle_block=bounty.expiration)
        s.add(b)
        try:
            s.flush()
        except IntegrityError:
            # Bounty already exists, ignore
            log.debug("Bounty %s already exists", bounty.guid)
            s.close()
            return
        log.info("New bounty %s with %s artifact(s) | Settle at %s", bounty.guid,
                  len(manifest), bounty.expiration)

        # Create jobs for every backend.  If new backends join or backends are
        # removed, tasks are *not* automatically updated.
        job_ids = []
        for artifact in manifest:
            a = DbArtifact(bounty_id=b.id,
                           hash=artifact["hash"],
                           name=artifact["name"])
            s.add(a)
            s.flush()
            job_ids.append(a.id)

            jobs = []
            # TODO: analysis_backends may change during different runs
            for backend in analysis_backends.values():
                v = DbArtifactVerdict(artifact_id=a.id,
                                      backend=backend.name,
                                      status=JOB_STATUS_NEW)
                s.add(v)
                jobs.append(v)
            s.flush()
        s.commit()
        s.close()

        for i, artifact in enumerate(manifest):
            # TODO: this is just the way their API works
            # TODO: parallel download
            ipfs_download(artifact["hash"],
                          "%s/%s" % (bounty.uri, i))

        # Now that we have a bounty, we need to fetch the artifacts and
        # start submitting it
        for job in job_ids:
            dispatch_event("verdict_jobs", (bounty.guid, job))

    @event("bounty_artifact_verdict")
    def bounty_artifact_verdict(self, bounty_id):
        """Check if bounty can be settled after artifact update"""

        s = DbSession()
        bounty = s.query(DbBounty).with_for_update() \
            .filter_by(id=bounty_id).one()
        if bounty.truth_value is not None:
            log.debug("%s | Bounty was already settled, nothing to do",
                      bounty.guid)
            s.close()
            return

        artifacts = s.query(DbArtifact).filter_by(bounty_id=bounty_id) \
            .order_by(DbArtifact.id).all()
        verdicts = []
        can_settle = True
        for artifact in artifacts:
            if artifact.verdict is None:
                log.debug("%s | Artifact #%s still has no verdict", bounty.guid,
                          artifact.id)
                can_settle = False
                break
            elif artifact.verdict >= 50:
                verdicts.append(True)
            else:
                verdicts.append(False)
        if can_settle:
            log.debug("%s | Recording verdict: %s", bounty.guid,
                      verdict_show(verdicts))
            bounty.truth_value = verdicts
            s.add(bounty)
            s.commit()
        s.close()
        if can_settle:
            dispatch_event("check_settle")

def fix_bitlist(lst, n):
    while len(lst) < n:
        lst.append(False)
    return lst[:n]
