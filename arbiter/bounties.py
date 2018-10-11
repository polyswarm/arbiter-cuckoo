# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import datetime
import logging
import gevent

from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, and_

from arbiter.backends import analysis_backends
from arbiter.component import Component
from arbiter.const import JOB_STATUS_NEW, VERDICT_MAYBE
from arbiter.database import DbSession, DbBounty, DbArtifact, DbArtifactVerdict
from arbiter.events import event, periodic, dispatch_event
from arbiter.ipfs import ipfs_json, ipfs_download, IPFSNotFoundError
from arbiter.polyswarm_api import PolySwarmError, PolySwarmNotFound
from arbiter.utils import pct_agree, verdict_show, verdict_compare

log = logging.getLogger(__name__)

ARBITER_VOTE_WINDOW = 25
ASSERTION_REVEAL_WINDOW = 25

def bounty_settle_manual(guid, verdicts):
    s = DbSession()
    bounty = s.query(DbBounty).with_for_update().filter_by(guid=guid).first()

    if not bounty:
        s.close()
        raise KeyError("No such bounty")
    elif bounty.voted or bounty.settled:
        s.close()
        raise ValueError("Bounty was already voted on/settled")

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

def _add_event(events, lst, key, name, *args):
    if key not in lst:
        lst.add(key)
        events.append((name, args))
    else:
        log.debug("Skip %s %s (pending)", name, key)

class BountyComponent(Component):
    """Keep track of bounties"""
    def __init__(self, parent):
        self.manual_mode = parent.manual_mode
        self.polyswarm = parent.polyswarm
        self.expires = parent.config.expires
        self.cur_block = None

        self.trusted_experts = parent.config.trusted_experts
        self.untrusted_experts_required = 3

        # Task list (TODO: not multi-process friendly)
        self.is_revealing = set()
        self.is_voting = set()
        self.is_settling = set()

    @event("block")
    def block_updated(self, block_number):
        """Advance to the next block.

        Dispatches tasks that depend on a particular block threshold to have
        passed, and also tasks that failed due to temporary errors (not ideal).
        We could replace it with a task log/queue with block number.

        This will refetch things that are still in-progress, which should not
        be an issue unless the block mining rate is very high.
        """
        if self.cur_block is not None and block_number <= self.cur_block:
            return
        self.cur_block = block_number

        # TODO: maybe conflict with tasks spawned elsewhere

        s = DbSession()

        bounties = s.query(DbBounty).filter_by(status="active") \
            .filter(or_(
                # Can vote
                and_(DbBounty.voted.is_(False), self.cur_block >= DbBounty.expiration_block, DbBounty.truth_value.isnot(None)),
                # Can reveal (independent from voting)
                and_(DbBounty.revealed.is_(False), self.cur_block >= DbBounty.reveal_block, DbBounty.assertions.is_(None)),
                # Can settle (must have voted)
                and_(DbBounty.voted.is_(True), DbBounty.assertions.isnot(None), DbBounty.settled.is_(False), self.cur_block >= DbBounty.settle_block),
            ))

        events = []
        for b in bounties:
            if not b.voted and b.truth_value is not None:
                _add_event(events, self.is_voting, b.guid,
                           "bounty_vote", b.guid, b.truth_value, b.vote_block)
            if not b.revealed and self.cur_block >= b.reveal_block:
                _add_event(events, self.is_revealing, b.guid,
                           "bounty_assertions_reveal", b.guid, b.truth_value)
            if b.voted and b.revealed and not b.settled and self.cur_block >= b.settle_block:
                _add_event(events, self.is_settling, b.guid,
                           "bounty_settle", b.guid)
        s.close()

        for e, args in events:
            dispatch_event(e, *args)

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

    @event("bounty_vote", serialize=False)
    def bounty_vote(self, guid, value, vote_block):
        """Propagate bounty vote value to PolySwarm"""
        if not value:
            log.error("%s | Bad bounty_vote call %r", guid, value)
            self.is_voting.discard(guid)
            return

        log.info("%s | Vote on bounty: %s", guid, verdict_show(value))
        try:
            self.polyswarm.vote_bounty(guid, value)
            perm_fail = False
        except PolySwarmError as e:
            log.error("%s | Voting error: %s", guid, e.message or e.reason)
            if e.status >= 500 and self.cur_block < vote_block:
                # Server booboo, so try again later
                self.is_voting.discard(guid)
                return
            # Abort
            perm_fail = True

        # TODO: if voting took place >= bounty.vote_block and we didn't manage
        # to, we've failed!

        s = DbSession()
        bounty = s.query(DbBounty).with_for_update().filter_by(guid=guid).one()
        if not bounty.voted:
            # Fail-safe against double vote bugs
            bounty.voted = True
            if perm_fail:
                bounty.status = "aborted"
                # TODO: WS event
            s.add(bounty)
        s.commit()
        s.close()

        self.is_voting.discard(guid)

    @event("bounty_assertions_reveal", serialize=False)
    def bounty_assertions_reveal(self, guid, value):
        """Reveal assertions.
        We should have already voted."""
        log.debug("%s | Checking assertions", guid)

        experts_disagree = False
        assertions = []
        try:
            assertions = self.polyswarm.bounty_assertions(guid)
            if value:
                experts_disagree = self._bounty_assertions_disagree(guid, value, assertions)
        except PolySwarmNotFound:
            pass
        except PolySwarmError as e:
            log.exception("%s | Assertion fetch error: %s", guid, e)
        except:
            # We ignore this for now
            log.exception("Failed to check assertions")

        if assertions:
            log.debug("%s | %s assertion(s)", guid, len(assertions))

        s = DbSession()
        bounty = s.query(DbBounty).with_for_update() \
            .filter_by(guid=guid).one()
        bounty.revealed = True
        bounty.assertions = assertions

        if experts_disagree and not bounty.settled:
            # Mark as manual so we don't auto-settle
            log.warning("%s | Set to manual", guid)
            bounty.truth_manual = True

        settle_block = bounty.settle_block
        s.add(bounty)
        s.commit()
        s.close()

        self.is_revealing.discard(guid)

        if not experts_disagree:
            # Dispatch bounty_settle so we don't have to wait for another
            # block update
            if value is not None and self.cur_block >= settle_block and guid not in self.is_settling:
                self.is_settling.add(guid)
                dispatch_event("bounty_settle", guid)
        else:
            dispatch_event("bounty_manual", guid)

    @event("bounty_settle", serialize=False)
    def bounty_settle(self, guid):
        """Settle bounty for payout"""

        log.info("%s | Settle bounty", guid)
        try:
            self.polyswarm.settle_bounty(guid)
        except PolySwarmNotFound:
            # Record permanent failure
            log.error("%s | Bounty no longer exists (double submit?)", guid)
        except PolySwarmError as e:
            log.error("%s | API error: %s", guid, e)
            self.is_settling.discard(guid)
            return
        except:
            log.exception("Failed to settle bounty")
            self.is_settling.discard(guid)
            return

        s = DbSession()
        bounty = s.query(DbBounty).with_for_update() \
            .filter_by(guid=guid).one()
        if not bounty.settled:
            bounty.status = "finished"
            bounty.settled = True
            s.add(bounty)
        s.commit()
        s.close()

        self.is_settling.discard(guid)
        dispatch_event("bounty_settled", guid)

    @event("bounty", serialize=32)
    def bounty_with_manifest(self, bounty):
        """A bounty has become available: register it for processing"""

        if bounty.get("resolved"):
            return

        # Download related files
        try:
            manifest = ipfs_json(bounty["uri"], cache=False)
        except IPFSNotFoundError:
            # Shouldn't happen in production
            return
        except:
            # TODO: track some well-known issues (e.g. disk full, ...)
            # TODO: right now we'll skip these bounties!
            log.warning("Couldn't fetch artifact data for bounty %s", bounty["guid"])
            return

        # {hash, name}, both matter
        manifest = manifest["result"]
        if not manifest:
            log.warning("Bounty %s has no artifacts", bounty["guid"])
            return

        # TODO Reintroduce explicit checking of artifact count.
        # if len(manifest) != bounty["num_artifacts"]:
        #     log.warning(
        #         "Bounty %s has manifest with %s entries, but claims %s",
        #         bounty["guid"], len(manifest), bounty["num_artifacts"])
        #     return
        num_artifacts = len(manifest)
        expiration = int(bounty["expiration"])

        s = DbSession()
        b = DbBounty(
            guid=bounty["guid"],
            author=bounty["author"],
            amount=bounty["amount"],
            num_artifacts=num_artifacts,

            expiration_block=expiration,
            vote_block=expiration + self.polyswarm.vote_window,
            reveal_block=expiration + self.polyswarm.vote_window + self.polyswarm.reveal_window,
            settle_block=expiration + self.polyswarm.vote_window + self.polyswarm.reveal_window
        )

        if self.manual_mode:
            b.truth_manual = True
        s.add(b)
        try:
            s.flush()
        except IntegrityError:
            # log.error("%s => %s", bounty["guid"], e)
            # Bounty already exists, ignore
            log.debug("Bounty %s already exists", bounty["guid"])
            s.close()
            return

        log.info("New bounty %s with %s artifact(s)", bounty["guid"], len(manifest))

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

        artifacts = []
        for i, artifact in enumerate(manifest):
            # TODO: this is just the way their API works
            # TODO: parallel download
            artifacts.append(gevent.spawn(ipfs_download,
                                          artifact["hash"],
                                          "%s/%s" % (bounty["uri"], i)))
        gevent.joinall(artifacts)
        for a in artifacts:
            if a.exception is not None:
                # TODO: we should abort here
                log.warning("Downloading artifacts for %s not succesful!",
                            bounty["guid"])
                break

        # Now that we have a bounty, we need to fetch the artifacts and
        # start submitting it
        for job in job_ids:
            dispatch_event("verdict_jobs", bounty["guid"], job)

    @event("bounty_artifact_verdict")
    def bounty_artifact_verdict(self, bounty_id):
        """Check if bounty can be voted on after artifact update"""

        s = DbSession()
        bounty = s.query(DbBounty).with_for_update() \
            .filter_by(id=bounty_id).one()
        if bounty.truth_value is not None:
            log.warning("%s | Bounty already has truth value, nothing to do",
                        bounty.guid)
            s.close()
            return
        elif bounty.truth_manual:
            # Already manual, so it won't make a difference
            s.close()
            return

        # This may happen *after* the voting window, in that case mark
        # the bounty as aborted
        if self.cur_block and self.cur_block >= bounty.vote_block:
            guid = None
            if bounty.status != "aborted":
                log.error("%s | Bounty artifact verdicts came in too late:"
                          " at block %s, voting ended on %s!",
                          bounty.guid, self.cur_block, bounty.vote_block)
                bounty.status = "aborted"
                guid = bounty.guid
                s.add(bounty)
                s.commit()
            s.close()
            if guid:
                dispatch_event("bounty_aborted", guid)
            return

        # Collect verdicts
        guid = bounty.guid
        artifacts = s.query(DbArtifact).filter_by(bounty_id=bounty_id) \
            .order_by(DbArtifact.id).all()
        verdicts = []
        record_value = True
        can_vote = self.cur_block and self.cur_block >= bounty.expiration_block
        transition_manual = False
        for artifact in artifacts:
            if not artifact.processed:
                log.debug("%s | Artifact #%s still has no verdict", bounty.guid,
                          artifact.id)
                record_value = can_vote = False
                break
            elif artifact.verdict is None:
                log.debug("%s | Artifact #%s has DONTKNOW verdict", bounty.guid,
                          artifact.id)
                can_vote = False
                transition_manual = True
            elif artifact.verdict >= VERDICT_MAYBE:
                verdicts.append(True) # Malicious
            else:
                verdicts.append(False) # Safe

        # Assertions can no longer come in before we've voted
        ## In case artifact verdicts came in after settle block
        #if bounty.assertions and not transition_manual:
        #    transition_manual = self._bounty_assertions_disagree(bounty.guid, verdicts, bounty.assertions)
        vote_block = bounty.vote_block

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
        if can_vote and verdicts and guid not in self.is_voting:
            self.is_voting.add(guid)
            dispatch_event("bounty_vote", guid, verdicts, vote_block)
        if transition_manual:
            dispatch_event("bounty_manual", guid)

def fix_bitlist(lst, n):
    while len(lst) < n:
        lst.append(False)
    return lst[:n]
