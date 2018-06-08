# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import datetime
import logging
import mock
import pytest
import uuid

from arbiter import verdicts
from arbiter.backends import AnalysisBackend
from arbiter.const import (
    VERDICT_DONTKNOW, VERDICT_SAFE, VERDICT_MALICIOUS, JOB_STATUS_FAILED,
    JOB_STATUS_DONE, JOB_STATUS_NEW, JOB_STATUS_SUBMITTING, JOB_STATUS_PENDING
)
from arbiter.database import DbSession, DbBounty, DbArtifact, DbArtifactVerdict
from arbiter.verdicts import majority23, vote_on_artifact, VerdictComponent

from utils import db_init, db_destroy, db_clear

@pytest.fixture(scope="module")
def db():
    try:
        db_init()
        yield
    finally:
        db_destroy()

class artifact:
    def __init__(self, with_verdicts={}):
        self.with_verdicts = with_verdicts

    def __enter__(self):
        s = DbSession()
        g = str(uuid.uuid4())
        b = DbBounty(guid=g,
                     expires=datetime.datetime.utcnow() + datetime.timedelta(days=1),
                     settle_block=1000)
        s.add(b)
        s.flush()
        bid = b.id
        a = DbArtifact(bounty_id=b.id,
                       hash="Q121293810",
                       name="dummy.exe")
        s.add(a)
        s.flush()
        aid = a.id

        jobs = []
        for backend, attr in self.with_verdicts.items():
            av = DbArtifactVerdict(artifact_id=aid,
                                   status=JOB_STATUS_DONE,
                                   backend=backend)
            for k, v in attr.items():
                setattr(av, k, v)
            s.add(av)
            s.flush()
            jobs.append([av.id, backend, None])

        s.commit()
        s.close()
        return {"bid": bid, "guid": g, "artifact_id": aid, "jobs": jobs}

    def __exit__(self, *args):
        s = DbSession()
        s.query(DbBounty).delete()
        s.commit()
        s.close()

class Holder:
    pass

class Config:
    expires = datetime.timedelta(days=5)
    url = "http://localhost:59999/"

class Parent:
    polyswarm = Holder()
    config = Config()

def test_majority23():
    assert not majority23(0, 0)
    assert majority23(1, 1)
    assert majority23(67, 100)
    assert not majority23(66, 100)

def test_vote_hc(caplog):
    caplog.set_level(logging.INFO)

    verdicts.analysis_backends = {}
    assert vote_on_artifact({}) is VERDICT_DONTKNOW
    assert vote_on_artifact({"doesnotexist": VERDICT_MALICIOUS}) is VERDICT_DONTKNOW

    verdicts.analysis_backends = {
        "cuckoo": AnalysisBackend("cuckoo", True, 1),
        "zer0m0n": AnalysisBackend("zer0mon", True, 1),
        "antivirus": AnalysisBackend("antivirus", True, 1),
        "modified": AnalysisBackend("modified", False, 1),
        "cape": AnalysisBackend("cape", False, 2),
        "clamav": AnalysisBackend("clamav", False, 1),
    }
    assert vote_on_artifact({"cuckoo": VERDICT_MALICIOUS}) == VERDICT_MALICIOUS
    assert vote_on_artifact({"doesnotexist": VERDICT_MALICIOUS}) is VERDICT_DONTKNOW
    assert vote_on_artifact({"modified": VERDICT_SAFE,
                             "cape": VERDICT_SAFE,
                             "clamav": VERDICT_SAFE}) == VERDICT_SAFE
    assert vote_on_artifact({"modified": VERDICT_MALICIOUS,
                             "cape": VERDICT_MALICIOUS,
                             "clamav": VERDICT_MALICIOUS}) == VERDICT_MALICIOUS
    assert vote_on_artifact({"cuckoo": VERDICT_SAFE,
                             "zer0m0n": VERDICT_SAFE,
                             "antivirus": VERDICT_SAFE,
                             "modified": VERDICT_MALICIOUS,
                             "cape": VERDICT_MALICIOUS,
                             "clamav": VERDICT_MALICIOUS}) == VERDICT_MALICIOUS
    # No real majority
    assert vote_on_artifact({"modified": VERDICT_MALICIOUS,
                             "cape": VERDICT_SAFE,
                             "clamav": VERDICT_MALICIOUS}) == VERDICT_SAFE

    assert vote_on_artifact({"modified": VERDICT_SAFE,
                             "cape": VERDICT_MALICIOUS,
                             "clamav": VERDICT_MALICIOUS}) == VERDICT_MALICIOUS

@mock.patch("arbiter.verdicts.dispatch_event")
def test_expire_verdicts(dispatch_event, db):
    v = VerdictComponent(Parent())
    verdicts.analysis_backends = {
        u"cuckoo": AnalysisBackend(u"cuckoo", True, 1),
        u"zer0m0n": AnalysisBackend(u"zer0m0n", False, 1),
    }

    expire_at = datetime.datetime.utcnow() - datetime.timedelta(hours=1)

    mixed = artifact({u"cuckoo": {"status": JOB_STATUS_PENDING,
                                  "expires" : expire_at},
                      u"zer0m0n": {"status": JOB_STATUS_DONE,
                                   "expires": expire_at}})
    with mixed:
        v.expire_verdicts()
        assert dispatch_event.called

        s = DbSession()
        try:
            for av in s.query(DbArtifactVerdict):
                if av.backend == "cuckoo":
                    assert av.status == JOB_STATUS_FAILED
                else:
                    assert av.status == JOB_STATUS_DONE
        finally:
            s.close()
    db_clear()

def test_retry_submission():
    pass

@mock.patch("arbiter.verdicts.dispatch_event")
def test_verdict_update(dispatch_event, db):
    v = VerdictComponent(Parent())
    verdicts.analysis_backends = {
        u"cuckoo": AnalysisBackend(u"cuckoo", True, 1),
        u"zer0m0n": AnalysisBackend(u"zer0m0n", False, 1),
    }

    incomplete = artifact({u"cuckoo": {"status": JOB_STATUS_DONE,
                                      "verdict": VERDICT_SAFE},
                           u"zer0m0n": {"status": JOB_STATUS_PENDING}})
    with incomplete as x:
        v.verdict_update(x["artifact_id"])
        assert not dispatch_event.called

    complete = artifact({u"cuckoo": {"status": JOB_STATUS_DONE,
                                     "verdict": VERDICT_SAFE},
                         u"zer0m0n": {"status": JOB_STATUS_DONE,
                                      "verdict": VERDICT_SAFE}})
    with complete as x:
        v.verdict_update(x["artifact_id"])
        dispatch_event.assert_called_with("bounty_artifact_verdict", (x["bid"],))

@mock.patch("arbiter.verdicts.dispatch_event")
def test_verdict_jobs(dispatch_event, db):
    v = VerdictComponent(Parent())
    verdicts.analysis_backends = {
        u"cuckoo": AnalysisBackend(u"cuckoo", True, 1),
        u"zer0m0n": AnalysisBackend(u"zer0m0n", False, 1),
    }

    pending = artifact({u"cuckoo": {"status": JOB_STATUS_NEW},
                        u"zer0m0n": {"status": JOB_STATUS_NEW}})
    with pending as x:
        v.verdict_jobs(x["guid"], x["artifact_id"])
        assert dispatch_event.called

@mock.patch("arbiter.verdicts.dispatch_event")
def test_verdict_job_submit(dispatch_event, db):
    v = VerdictComponent(Parent())
    verdicts.analysis_backends = {
        u"cuckoo": AnalysisBackend(u"cuckoo", True, 1),
        u"zer0m0n": AnalysisBackend(u"zer0m0n", False, 1),
        u"cuckscan": AnalysisBackend(u"cuckscan", False, 1),
    }

    verdicts.analysis_backends[u"cuckoo"].submit_artifact = lambda a: None
    verdicts.analysis_backends[u"zer0m0n"].submit_artifact = lambda a: {}
    verdicts.analysis_backends[u"cuckscan"].submit_artifact = lambda a: 1

    pending = artifact({u"cuckoo": {"status": JOB_STATUS_SUBMITTING},
                        u"zer0m0n": {"status": JOB_STATUS_SUBMITTING},
                        u"cuckscan": {"status": JOB_STATUS_SUBMITTING}})
    with pending as x:
        v.verdict_job_submit(x["artifact_id"], x["jobs"])
        assert dispatch_event.called
        s = DbSession()
        try:
            for av in s.query(DbArtifactVerdict):
                if av.backend == "cuckscan":
                    assert av.status == JOB_STATUS_DONE
                else:
                    assert av.status == JOB_STATUS_PENDING
        finally:
            s.close()
    db_clear()

def test_reset_pending_jobs():
    pass
