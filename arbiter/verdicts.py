# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

"""
Verdict states:

* New: not yet submitted
* Submitting: being submitted, guards against parallel duplicated submission
* Pending: currently awaiting response
* Failed: analysis backend broke
* Done: has a verdict
"""

import datetime
import gevent
import logging

from arbiter.artifacts import Artifact
from arbiter.backends import analysis_backends
from arbiter.component import Component
from arbiter.const import (
    JOB_STATUS_DONE, JOB_STATUS_NEW, JOB_STATUS_SUBMITTING,
    JOB_STATUS_PENDING, JOB_STATUS_FAILED, VERDICT_DONTKNOW,
    VERDICT_SAFE, VERDICT_MAYBE, VERDICT_MALICIOUS
)
from arbiter.database import DbSession, DbArtifact, DbArtifactVerdict
from arbiter.events import periodic, event, dispatch_event

log = logging.getLogger(__name__)

def majority23(v, n):
    if not n:
        return False
    req = 2.0 * (n / 3.0)
    return v >= req

def vote_on_artifact(voters):
    """Tiered voting algorithm. Patent pending."""
    high_confidence_malicious = False

    votes = 0
    total_weight = 0
    total_votes = 0
    total_voters = 0

    log.debug("%r %r", analysis_backends.keys(),
              voters.keys())

    # TODO: not sensible when high-confidence voters all vote safe,
    # or broken when there are no low-confidence voters
    for a in analysis_backends.values():
        vote = voters.get(a.name)
        log.debug("%r %r", a.name, vote)
        if not a.trusted:
            # This will be messy
            total_weight += a.weight * VERDICT_MALICIOUS
            total_voters += 1
        if vote is not None:
            if not a.trusted:
                total_votes += 1
                votes += a.weight * vote
            else:
                if vote >= VERDICT_MAYBE:
                    high_confidence_malicious = True

    if high_confidence_malicious:
        log.info("Voted MALICIOUS because of positive high-confidence voter")
        return VERDICT_MALICIOUS

    if not majority23(total_votes, total_voters):
        log.info("Voted DONTKNOW because there are missing voters (%s/%s)",
                 total_votes, total_voters)
        return VERDICT_DONTKNOW

    if majority23(votes, total_weight):
        log.info("Voted MALICIOUS because of majority low-confidence voters"
                 " (%s/%s)", votes, total_weight)
        return VERDICT_MALICIOUS

    log.info("Voted SAFE because of majority low-confidence voters (%s/%s)",
             votes, total_weight)
    return VERDICT_SAFE

class VerdictComponent(Component):
    def __init__(self, parent):
        self.expires = parent.config.expires
        self.url = parent.config.url

    @periodic(minutes=2)
    def expire_verdicts(self):
        """Expire pending verdict tasks."""
        notify_tasks = []
        now = datetime.datetime.utcnow()
        s = DbSession()
        avs = s.query(DbArtifactVerdict).with_for_update() \
            .filter_by(status=JOB_STATUS_PENDING) \
            .filter(DbArtifactVerdict.expires < now)
        for av in avs:
            log.warning("Job %s expired", av.id)
            av.status = JOB_STATUS_FAILED
            s.add(av)
            notify_tasks.append([av.backend, av.artifact_id, av.meta])
        s.commit()
        s.close()
        if notify_tasks:
            dispatch_event("verdict_retry", notify_tasks)

    # TODO: we can retry jobs with failed submissions:
    @periodic(minutes=2)
    def retry_submissions(self):
        """
        Conditions:
        * Failure was temporary
        * Bounty is not about to expire
        """
        s = DbSession()
        avs = [a.artifact_id for a in
               s.query(DbArtifactVerdict.artifact_id) \
               .filter_by(status=JOB_STATUS_NEW)]
        s.close()
        for a in avs:
            dispatch_event("verdict_jobs", (None, a,))

    @event("verdict_update")
    def verdict_update(self, artifact_id):
        """Recompute final verdict for an artifact and trigger bounty settle if
        needed.

        Verdicts that were updated must belong to the same bounty and the same
        artifact within that bounty."""
        log.debug("Artifact #%s updated", artifact_id)

        s = DbSession()

        artifact = s.query(DbArtifact).with_for_update() \
            .filter_by(id=artifact_id).one()
        verdicts = s.query(DbArtifactVerdict).filter_by(artifact_id=artifact_id)
        bounty_id = artifact.bounty_id
        incomplete = False

        verdict_map = {}
        for verdict in verdicts.all():
            if verdict.status > JOB_STATUS_DONE:
                incomplete = True
            verdict_map[verdict.backend] = verdict.verdict

        if not incomplete:
            log.info("Verdict for artifact #%s can be made: %r", artifact_id,
                     verdict_map)
            verdict = vote_on_artifact(verdict_map)
            if verdict is not None:
                log.info("Verdict: %r", verdict)
                artifact.verdict = verdict
                s.add(artifact)
                s.commit()
            else:
                log.debug("Verdict for artifact #%s failed", artifact_id)
                # TODO: move bounty to manual mode
                bounty_id = None
        else:
            log.debug("Verdict for artifact #%s incomplete", artifact_id)
            bounty_id = None
        s.close()
        if bounty_id is not None:
            dispatch_event("bounty_artifact_verdict", (bounty_id,))

    @event("verdict_jobs", serialize=False)
    def verdict_jobs(self, bounty_guid, artifact_id):
        """Jobs to submit or otherwise check"""
        submit = []

        # Find jobs we need to submit, and mark them
        s = DbSession()
        a = s.query(DbArtifact).filter_by(id=artifact_id).one()
        artifact = Artifact(a.id, a.name, a.hash,
                            "%s/artifact/%s" % (self.url, a.id))
        avs = s.query(DbArtifactVerdict).with_for_update() \
            .filter_by(artifact_id=artifact.id, status=JOB_STATUS_NEW)

        for av in avs.all():
            submit.append((av.id, av.backend, artifact))
            av.status = JOB_STATUS_SUBMITTING
            s.add(av)

        s.commit()
        s.close()

        dispatch_event("verdict_job_submit", (artifact_id, submit))

    @event("verdict_job_submit", serialize=False)
    def verdict_job_submit(self, artifact_id, jobs):
        tasks = []
        task_ids = {}
        job_status = {}
        exp = datetime.datetime.utcnow() + self.expires
        failed = {DbArtifactVerdict.status: JOB_STATUS_FAILED,
                  DbArtifactVerdict.meta: None,
                  DbArtifactVerdict.expires: None}

        try:
            for av_id, backend, artifact in jobs:
                # Just in case a backend is removed
                a = analysis_backends.get(backend)
                if a:
                    log.debug("Submitting job #%s to %s", av_id, backend)
                    task = gevent.spawn(a.submit_artifact, artifact)
                    task_ids[id(task)] = av_id
                    tasks.append(task)
                else:
                    log.warning("%r", backend)

            # Collect results
            gevent.joinall(tasks)
            for task in tasks:
                av_id = task_ids[id(task)]
                if task.exception is not None:
                    job_status[av_id] = failed
                elif isinstance(task.value, int):
                    job_status[av_id] = {DbArtifactVerdict.status: JOB_STATUS_DONE,
                                         DbArtifactVerdict.verdict: task.value,
                                         DbArtifactVerdict.meta: None,
                                         DbArtifactVerdict.expires: None}
                else:
                    job_status[av_id] = {DbArtifactVerdict.status: JOB_STATUS_PENDING,
                                         DbArtifactVerdict.meta: task.value,
                                         DbArtifactVerdict.expires: exp}

        finally:
            # Record results
            s = DbSession()
            reeval = False
            for av_id, backend, artifact in jobs:
                fields = job_status.get(av_id, failed)
                status = fields[DbArtifactVerdict.status]
                log.debug("Recording job result #%s of %s (r=%s)", av_id,
                          backend, status)

                # The submission process is subject to a race condition where
                # we may receive the callback before all submissions are
                # complete, so prevent incorrectly updating items.
                s.query(DbArtifactVerdict) \
                    .filter_by(id=av_id, status=JOB_STATUS_SUBMITTING) \
                    .update(fields, synchronize_session=False)
                if status == JOB_STATUS_DONE:
                    reeval = True

            s.commit()
            s.close()

            if reeval:
                dispatch_event("verdict_update", (artifact_id,))

def reset_pending_jobs():
    """
    Reset jobs that were pending submission.  This may result in jobs being
    submitted twice when the arbiter is restarted.
    """
    log.debug("Reset pending jobs")
    # TODO: this is incompatible with a multi-process approach

    s = DbSession()
    s.query(DbArtifactVerdict) \
        .filter_by(status=JOB_STATUS_PENDING) \
        .update({DbArtifactVerdict.status: JOB_STATUS_NEW}, synchronize_session=False)
    s.commit()
    s.close()
