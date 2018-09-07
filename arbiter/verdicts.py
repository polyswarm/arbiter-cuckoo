# Copyright (C) 2018 Hatching B.V.
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
import time

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
from arbiter.utils import pct_agree

log = logging.getLogger(__name__)

def interval(t, step_time=900):
    t = int(t)
    return t + step_time - (t % step_time)

def vote_on_artifact(voters):
    """Weighted voting system. Certain trusted voters can shortcut the voting
    process on malicious samples."""
    high_confidence_malicious = False

    votes = 0
    total_weight = 0
    total_votes = 0
    total_voters = 0

    for a in analysis_backends.values():
        vote = voters.get(a.name)
        total_voters += 1

        if vote is not None:
            total_weight += a.weight * VERDICT_MALICIOUS
            total_votes += 1
            votes += a.weight * vote

            if a.trusted and vote >= VERDICT_MAYBE:
                high_confidence_malicious = True

    if high_confidence_malicious:
        # We assume the backends are conservative, so if we trust this backend
        # has found sufficient evidence of malicious behavior, use this verdict
        log.info("Voted MALICIOUS because of positive high-confidence voter")
        return VERDICT_MALICIOUS

    if not pct_agree(0.5, total_votes, total_voters):
        # If too many voters abstain, we can't reach a verdict.
        log.info("Voted DONTKNOW because there are missing voters (%s/%s)",
                 total_votes, total_voters)
        return VERDICT_DONTKNOW

    if pct_agree(0.6666, votes, total_weight):
        # 66.6% or higher
        log.info("Voted MALICIOUS because of majority voters (%s/%s)", votes,
                 total_weight)
        return VERDICT_MALICIOUS

    if pct_agree(0.6666, total_weight - votes, total_weight):
        # 33.3% or lower
        log.info("Voted SAFE because of majority voters (%s/%s)", votes,
                 total_weight)
        return VERDICT_SAFE

    log.info("Voted DONTKNOW because of voters didn't agree (%s/%s)", votes,
             total_weight)
    return VERDICT_DONTKNOW

class VerdictComponent(Component):
    def __init__(self, parent):
        self.artifact_interval = parent.artifact_interval
        self.expires = parent.config.expires
        self.url = parent.config.url

    @periodic(minutes=2)
    def expire_verdicts(self):
        """Expire pending verdict tasks."""
        # TODO: preferably replace "arbitrary" timeout window with backend
        # polling
        notify_tasks = set()
        now = datetime.datetime.utcnow()
        s = DbSession()
        avs = s.query(DbArtifactVerdict).with_for_update() \
            .filter_by(status=JOB_STATUS_PENDING) \
            .filter(DbArtifactVerdict.expires < now)
        for av in avs:
            log.warning("Job %s expired", av.id)
            av.status = JOB_STATUS_FAILED
            # TODO: call backend.cancel_artifact
            s.add(av)
            notify_tasks.add(av.artifact_id)
        s.commit()
        s.close()
        for aid in notify_tasks:
            dispatch_event("verdict_update", aid)

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
            dispatch_event("verdict_jobs", None, a)

    @event("verdict_update_async")
    def verdict_update_async(self, artifact_verdict_id, verdict):
        """Internal polling has resulted in an artifact verdict."""
        s = DbSession()
        try:
            av = s.query(DbArtifactVerdict).with_for_update() \
                .get(artifact_verdict_id)
            artifact_id = av.artifact_id
            if av.status != JOB_STATUS_PENDING:
                log.warning("Task result for artifact #%s (%s) already made",
                            artifact_id, av.backend)
                return
            if verdict is False:
                log.warning("Task failed for artifact #%s (%s)", artifact_id,
                            av.backend)
                av.status = JOB_STATUS_FAILED
            else:
                log.debug("Task for artifact #%s (%s) complete", artifact_id,
                            av.backend)
                av.verdict = verdict
                av.status = JOB_STATUS_DONE
            s.add(av)
            s.commit()
            dispatch_event("verdict_update", artifact_id)
        finally:
            s.close()

    @event("verdict_update")
    def verdict_update(self, artifact_id):
        """Recompute final verdict for an artifact and trigger bounty settle if
        needed."""
        log.debug("Artifact #%s updated", artifact_id)

        s = DbSession()

        artifact = s.query(DbArtifact).with_for_update().get(artifact_id)
        if artifact.processed:
            log.warning("Verdict for artifact #%s already made", artifact_id)
            s.close()
            return

        verdicts = s.query(DbArtifactVerdict).filter_by(artifact_id=artifact_id)
        bounty_id = artifact.bounty_id
        incomplete = False

        verdict_map = {}
        for verdict in verdicts.all():
            if verdict.status > JOB_STATUS_DONE:
                incomplete = True
            verdict_map[verdict.backend] = verdict.verdict

        if not incomplete:
            log.debug("Verdict for artifact #%s can be made: %r", artifact_id,
                      verdict_map)
            verdict = vote_on_artifact(verdict_map)
            log.debug("Verdict for artifact #%s: %r", artifact_id, verdict)
            artifact.processed = True
            artifact.processed_at = datetime.datetime.utcnow()
            artifact.processed_at_interval = interval(time.time(), self.artifact_interval)
            artifact.verdict = verdict
            s.add(artifact)
            s.commit()
        else:
            log.debug("Verdict for artifact #%s incomplete", artifact_id)
            bounty_id = None
        s.close()
        if bounty_id is not None:
            dispatch_event("bounty_artifact_verdict", bounty_id)

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
            submit.append((av.id, av.backend, artifact, av.meta))
            av.status = JOB_STATUS_SUBMITTING
            s.add(av)

        s.commit()
        s.close()

        dispatch_event("verdict_job_submit", artifact_id, submit)

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
            for av_id, backend, artifact, previous_task in jobs:
                # Just in case a backend is removed
                a = analysis_backends.get(backend)
                if a:
                    log.debug("Submitting job #%s to %s", av_id, backend)
                    task = gevent.spawn(a.submit_artifact, av_id, artifact, previous_task)
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
                elif "verdict" in task.value:
                    verdict = task.value.pop("verdict")
                    job_status[av_id] = {DbArtifactVerdict.status: JOB_STATUS_DONE,
                                         DbArtifactVerdict.verdict: verdict,
                                         DbArtifactVerdict.meta: task.value,
                                         DbArtifactVerdict.expires: None}
                else:
                    job_status[av_id] = {DbArtifactVerdict.status: JOB_STATUS_PENDING,
                                         DbArtifactVerdict.meta: task.value,
                                         DbArtifactVerdict.expires: exp}

        finally:
            # Record results
            s = DbSession()
            reeval = False
            for av_id, backend, artifact, previous_task in jobs:
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
                if status <= JOB_STATUS_DONE:
                    reeval = True

            s.commit()
            s.close()

            if reeval:
                dispatch_event("verdict_update", artifact_id)

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
