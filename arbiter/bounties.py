# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import datetime
import logging

from sqlalchemy.exc import IntegrityError

from arbiter.backends import analysis_backends
from arbiter.component import Component
from arbiter.const import JOB_STATUS_NEW, VERDICT_MAYBE
from arbiter.database import DbSession, DbBounty, DbArtifact, DbArtifactVerdict
from arbiter.events import event, periodic, dispatch_event
from arbiter.ipfs import ipfs_json, ipfs_download, IPFSNotFoundError
from arbiter.polyswarm_api import Bounty, PolySwarmError, PolySwarmNotFound
from arbiter.utils import pct_agree, verdict_show, verdict_compare

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

        self.trusted_experts = parent.config.trusted_experts
        self.untrusted_experts_required = 3

        # Task list (TODO: not multi-process friendly)
        self.is_checking_assertions = set()

        # Bounties to settle
        self.pending_bounties = set()

    @periodic(minutes=1)
    def resubmit_pending_settle(self):
        if not self.cur_block:
            return
        resubmit = []
        s = DbSession()
        bounties = s.query(DbBounty.guid, DbBounty.truth_value) \
            .filter(DbBounty.settle_block <= self.cur_block) \
            .filter_by(truth_settled=False) \
            .filter(DbBounty.assertions.isnot(None)) \
            .filter(DbBounty.truth_value.isnot(None))
        for b in bounties:
            if b.guid not in self.pending_bounties:
                resubmit.append((b.guid, b.truth_value))
                self.pending_bounties.add(b.guid)
        s.close()
        if resubmit:
            log.info("Resubmit at %s: %s task(s)", self.cur_block,
                      len(resubmit))
        for guid, value in resubmit:
            dispatch_event("bounty_settle_attempt", guid, value)

    @event("block")
    def block_updated(self, block_number):
        """Advance to the next block."""
        if self.cur_block is not None and block_number <= self.cur_block:
            return
        self.cur_block = block_number

        # Try to fetch missing assertions first
        need_assertion_check = []
        s = DbSession()
        bounties = s.query(DbBounty.guid, DbBounty.truth_value) \
            .filter(self.cur_block >= DbBounty.settle_block) \
            .filter(DbBounty.assertions.is_(None))
        for b in bounties:
            if b.guid not in self.is_checking_assertions:
                need_assertion_check.append((b.guid, b.truth_value))
                self.is_checking_assertions.add(b.guid)
        s.close()

        for guid, value in need_assertion_check:
            dispatch_event("bounty_check_assertions", guid, value)

    def _bounty_assertions_disagree(self, guid, value, assertions):
        experts_disagree = False
        num_disagree = 0
        for a in assertions:
            verdicts = fix_bitlist(a["verdicts"], len(value))
            mask = fix_bitlist(a["mask"], len(value))
            compare = verdict_compare(value, verdicts, mask)
            if not compare:
                continue
            log.warning("%s | Expert %s disagrees! Their verdict: %s",
                        guid, a["author"], compare)
            num_disagree += 1
            if a["author"] in self.trusted_experts:
                experts_disagree = True
        if len(assertions) >= self.untrusted_experts_required:
            if pct_agree(0.6666, num_disagree, len(assertions)):
                log.warning("%s | Majority of experts disagrees! (%s/%s)", guid,
                            num_disagree, len(assertions))
                experts_disagree = True
        return experts_disagree

    @event("bounty_check_assertions", serialize=False)
    def bounty_check_assertions(self, guid, value):
        """Check if there are assertions that disagree with our verdict"""
        log.debug("%s | Checking assertions", guid)

        experts_disagree = False

        assertions = []
        try:
            assertions = self.polyswarm.bounty_assertions(guid)
            if value:
                experts_disagree = self._bounty_assertions_disagree(guid, value, assertions)
        except PolySwarmNotFound:
            pass
        except:
            # We ignore this for now
            log.exception("Failed to check assertions")

        if assertions:
            log.debug("%s | %s assertion(s)", guid, len(assertions))

        s = DbSession()
        bounty = s.query(DbBounty).with_for_update() \
            .filter_by(guid=guid).one()
        bounty.assertions = assertions

        if experts_disagree and not bounty.truth_settled:
            # Mark as manual
            log.warning("%s | Set to manual", guid)
            bounty.truth_manual = True

        s.add(bounty)
        s.commit()
        s.close()

        self.is_checking_assertions.discard(guid)

        if not experts_disagree:
            if value is not None:
                dispatch_event("bounty_settle_attempt", guid, value)
        else:
            dispatch_event("bounty_manual", guid)

    @event("bounty_settle_attempt", serialize=False)
    def bounty_settle_attempt(self, guid, value):
        """Submit final verdict to PolySwarm"""
        try:
            log.info("%s | Settle bounty value: %s", guid, verdict_show(value))
            try:
                self.polyswarm.settle_bounty(guid, value)
            except PolySwarmNotFound:
                # Record permanent failure
                log.error("%s | Bounty no longer exists (double submit?)", guid)
            except PolySwarmError as e:
                log.exception("%s | API error: %s", guid, e)
                return
            except:
                log.exception("Failed to settle bounty")
                return

            s = DbSession()
            bounty = s.query(DbBounty).with_for_update() \
                .filter_by(guid=guid).one()
            bounty.truth_settled = True
            s.add(bounty)
            s.commit()
            s.close()

        finally:
            self.pending_bounties.discard(guid)

        dispatch_event("bounty_settled", guid, value)

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
        dispatch_event("bounty_with_manifest", bounty)

    @event("bounty_with_manifest")
    def bounty_with_manifest(self, bounty):
        """A bounty has become available: register it for processing"""
        if bounty["resolved"]:
            # TODO: we can use this to abort pending tasks for this bounty
            return

        # Test:
        # - Expiry

        # {hash, name}, both matter
        manifest = ipfs_json(bounty["uri"])["result"]
        if not manifest:
            log.warning("Bounty %s has no artifacts", bounty["guid"])
            return

        deadline = datetime.datetime.utcnow() + self.expires

        s = DbSession()
        b = DbBounty(guid=bounty["guid"],
                     expires=deadline,
                     author=bounty["author"],
                     amount=bounty["amount"],
                     num_artifacts=len(manifest),
                     settle_block=bounty["expiration"])
        s.add(b)
        try:
            s.flush()
        except IntegrityError:
            # Bounty already exists, ignore
            log.debug("Bounty %s already exists", bounty["guid"])
            s.close()
            return
        log.info("New bounty %s with %s artifact(s) | Settle at %s",
                 bounty["guid"], len(manifest), bounty["expiration"])

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
                          "%s/%s" % (bounty["uri"], i))

        # Now that we have a bounty, we need to fetch the artifacts and
        # start submitting it
        for job in job_ids:
            dispatch_event("verdict_jobs", bounty["guid"], job)

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
        elif bounty.truth_manual:
            # Already manual, so it won't make a difference
            s.close()
            return

        guid = bounty.guid
        artifacts = s.query(DbArtifact).filter_by(bounty_id=bounty_id) \
            .order_by(DbArtifact.id).all()
        verdicts = []
        record_value = True
        can_settle = self.cur_block and self.cur_block >= bounty.settle_block
        transition_manual = False
        for artifact in artifacts:
            if not artifact.processed:
                log.debug("%s | Artifact #%s still has no verdict", bounty.guid,
                          artifact.id)
                record_value = can_settle = False
                break
            elif artifact.verdict is None:
                log.debug("%s | Artifact #%s has DONTKNOW verdict", bounty.guid,
                          artifact.id)
                can_settle = False
                transition_manual = True
            elif artifact.verdict >= VERDICT_MAYBE:
                verdicts.append(True) # Malicious
            else:
                verdicts.append(False) # Safe

        # In case artifact verdicts came in after settle block
        if bounty.assertions and not transition_manual:
            transition_manual = self._bounty_assertions_disagree(bounty.guid, verdicts, bounty.assertions)

        if transition_manual:
            log.debug("%s | Mark bounty as requiring manual verdict", bounty.guid)
            bounty.truth_manual = True
            s.add(bounty)
            s.commit()
        elif record_value:
            log.debug("%s | Recording verdict: %s", bounty.guid,
                      verdict_show(verdicts))
            bounty.truth_value = verdicts
            s.add(bounty)
            s.commit()
        s.close()
        if can_settle:
            self.pending_bounties.add(guid)
            dispatch_event("bounty_settle_attempt", guid, verdicts)
        if transition_manual:
            dispatch_event("bounty_manual", guid)

def fix_bitlist(lst, n):
    while len(lst) < n:
        lst.append(False)
    return lst[:n]
