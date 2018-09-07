# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import datetime
import mock
import pytest

from arbiter.backends import AnalysisBackend
from arbiter.bounties import (
    bounty_settle_manual, BountyComponent, fix_bitlist, PolySwarmError
)
from arbiter.database import DbSession, DbBounty, DbArtifact
from arbiter.ipfs import IPFSNotFoundError
from arbiter import bounties

from utils import db_init, db_destroy, db_clear

@pytest.fixture(scope="module")
def db():
    try:
        db_init()
        yield
    finally:
        db_destroy()

class Holder:
    pass

class Config:
    expires = datetime.timedelta(days=5)
    trusted_experts = []

class Parent:
    polyswarm = Holder()
    config = Config()

def _create_bounty(guid, truth_value=None, settled=False, n=0, assertions=None):
    s = DbSession()
    b = DbBounty(
        guid=guid,
        num_artifacts=n,
        assertions=n,
        expires=datetime.datetime.utcnow(),
        truth_value=truth_value,
        truth_settled=settled,
        settle_block=1001
    )
    s.add(b)
    s.flush()
    b_id = b.id
    a_ids = []
    for i in range(n):
        a = DbArtifact(bounty_id=b_id,
                       hash="%s" % i,
                       name="%s.txt" % i)
        s.add(a)
        s.flush()
        a_ids.append(a.id)
    s.commit()
    s.close()
    return b_id, a_ids

def _no_such_bounty(guid):
    s = DbSession()
    try:
        assert s.query(DbBounty).filter_by(guid=guid).count() == 0
    finally:
        s.close()

def _bounty_check_state(b, should_be_set, should_be_settled=None):
    s = DbSession()
    try:
        if isinstance(b, int):
            kwargs = {"id": b}
        else:
            kwargs = {"guid": b}
        b = s.query(DbBounty).filter_by(**kwargs).one()
        is_set = b.truth_value is not None
        is_settled = b.truth_settled is True
    finally:
        s.close()
    if not should_be_set and is_set:
        raise ValueError("Bounty %s was set, when it should not be" % b)
    elif should_be_set and not is_set:
        raise ValueError("Bounty %s was not set, when it should be" % b)
    if should_be_settled is None:
        return
    if not should_be_settled and is_settled:
        raise ValueError("Bounty %s was settled, when it should not be" % b)
    elif should_be_settled and not is_settled:
        raise ValueError("Bounty %s was not settled, when it should be" % b)

def _verdict_set(a_id, value):
    s = DbSession()
    try:
        s.query(DbArtifact).filter_by(id=a_id) \
            .update({DbArtifact.verdict: value})
        s.commit()
    finally:
        s.close()

def test_settle_manual(db):
    bad_guid = "0f0f0f0f-bbbb-cccc-dddd-000000000001"
    guid1 = "aaaaaaaa-bbbb-cccc-dddd-000000000001"
    guid2 = "aaaaaaaa-bbbb-cccc-dddd-000000000002"
    guid3 = "aaaaaaaa-bbbb-cccc-dddd-000000000003"
    truth_value = "[true]"
    _create_bounty(guid1, truth_value, True)
    _create_bounty(guid2, None, False, 1)
    _create_bounty(guid3, None, False, 2)
    try:
        with pytest.raises(KeyError):
            bounty_settle_manual(bad_guid, [True])
        with pytest.raises(ValueError):
            bounty_settle_manual(guid1, [True])
        # Should not raise
        bounty_settle_manual(guid2, [True])
        with pytest.raises(ValueError):
            bounty_settle_manual(guid3, [True])
    finally:
        db_clear()

@mock.patch("arbiter.bounties.dispatch_event")
def test_resubmit_pending_settle(dispatch_event, db):
    guid = "dda16db6-89eb-453b-8d0a-abababababab"
    truth_value = "[true]"
    _create_bounty(guid, truth_value, assertions=[])

    b = BountyComponent(Parent())

    try:
        b.resubmit_pending_settle()
        assert not dispatch_event.called

        b.cur_block = 1000
        b.resubmit_pending_settle()
        assert not dispatch_event.called

        b.cur_block = 1001
        b.resubmit_pending_settle()
        dispatch_event.assert_called_with("bounty_settle_attempt",
                                          guid, truth_value)
    finally:
        db_clear()

#@mock.patch("arbiter.bounties.dispatch_event")
#def test_block_updated(dispatch_event, db):
#    b = BountyComponent(Parent())
#    assert b.cur_block is None
#    b.block_updated(1001)
#    dispatch_event.assert_called_with("bounty_check_assertions")
#    dispatch_event.reset_mock()
#    b.block_updated(1000)
#    assert b.cur_block == 1001
#    assert not dispatch_event.called

def test_bounty_check_assertions(db):
    pass

def test_bounty_settle_attempt(db):
    b = BountyComponent(Parent())
    b.polyswarm.settle_bounty = mock.Mock()
    b.polyswarm.bounty_assertions = mock.Mock()
    b.polyswarm.bounty_assertions.return_value = []

    guid404 = "c8700c42-5833-4eb9-9330-6128574cbab8"
    guid = "f85fb0ed-7cd3-4f82-8627-e7e25b832336"
    truth_value = "[true]"
    b_id, _ = _create_bounty(guid, truth_value)
    b_id404, _ = _create_bounty(guid404, truth_value)

    b.pending_bounties.add(guid)
    b.pending_bounties.add(guid404)

    try:
        b.settle_bounty_attempt(guid, truth_value)
        assert guid not in b.pending_bounties
        _bounty_check_state(b_id, True, True)
        b.polyswarm.settle_bounty.assert_called_with(guid, truth_value)

        b.polyswarm.settle_bounty.reset_mock()
        b.polyswarm.settle_bounty.side_effect = PolySwarmError(404, 'Does not exist', 'NOT FOUND')

        # TODO: should have a marking
        b.settle_bounty_attempt(guid404, truth_value)
        assert guid404 not in b.pending_bounties
        _bounty_check_state(b_id404, True, True)
        b.polyswarm.settle_bounty.assert_called_with(guid404, truth_value)

    finally:
        db_clear()

@mock.patch("arbiter.bounties.ipfs_download")
@mock.patch("arbiter.bounties.dispatch_event")
def test_bounty_pre(dispatch_event, ipfs_download):
    b = BountyComponent(Parent())
    bounty = {"resolved": False,
              "guid": "88e5f4e6-e5e4-4dc3-88d0-c6a57ae13e1f",
              "uri": "QmcPMpDr1sR4fN28ZKwMbUMeUcoDB7cmYjFpVhpucTv7Rc"}
    b.bounty_pre(bounty)
    ipfs_download.assert_called_with(bounty["uri"])
    assert dispatch_event.called

    dispatch_event.reset_mock()
    ipfs_download.reset_mock()
    ipfs_download.side_effect = IPFSNotFoundError()
    bounty = {"resolved": False,
              "guid": "0a46a217-0e95-4ae7-a7eb-2e8e351c7f84",
              "uri": "QmamNsdX41A2xGEMHCL6eDzMzAK9rFdJWuTfxMsb21tBXM"}
    b.bounty_pre(bounty)
    ipfs_download.assert_called_with(bounty["uri"])
    assert not dispatch_event.called

    ipfs_download.reset_mock()
    ipfs_download.side_effect = IOError()
    bounty = {"resolved": False,
              "guid": "4587657d-5bfd-419c-8037-ffeb7f4467b4",
              "uri": "QmXhULzuSCDVQjJHqURTToqSRz6Y4BkVjJcRVJCHhJxGGX"}
    b.bounty_pre(bounty)
    ipfs_download.assert_called_with(bounty["uri"])
    assert not dispatch_event.called

@mock.patch("arbiter.bounties.ipfs_json")
@mock.patch("arbiter.bounties.ipfs_download")
@mock.patch("arbiter.bounties.dispatch_event")
def test_bounty_with_manifest(dispatch_event, ipfs_download, ipfs_json):
    b = BountyComponent(Parent())
    bounty = {
        "resolved": True,
        "amount": "10000",
        "author": "0xdeadbeef",
        "expiration": 222,
        "guid": "0d6a0d07-8424-4972-82fc-550266ff4da5",
        "uri": "Q1111",
        "verdicts": "[False]"
    }
    bounties.analysis_backends = {
        "cuckoo": AnalysisBackend("cuckoo", True, 1),
        "zer0m0n": AnalysisBackend("zer0m0n", True, 1),
    }
    try:
        # Unresolved ignored
        ipfs_json.return_value =  {"result": []}
        b.bounty_with_manifest(bounty)
        _no_such_bounty(bounty["guid"])

        # Empty manifest ignored
        bounty["resolved"] = False
        b.bounty_with_manifest(bounty)
        _no_such_bounty(bounty["guid"])

        ipfs_json.return_value =  {"result": [
            {"hash": "Q12312312",
             "name": "malwr.exe"}
        ]}
        b.bounty_with_manifest(bounty)
        _bounty_check_state(bounty["guid"], False, False)
    finally:
        db_clear()

@mock.patch("arbiter.bounties.dispatch_event")
def test_bounty_artifact_verdict(dispatch_event, db):
    guid = "35b1ee41-62e7-4e84-ae90-4e75cd6419c7"
    b_id, a_ids = _create_bounty(guid, n=2)

    b = BountyComponent(Parent())

    # Incomplete artifact
    b.bounty_artifact_verdict(b_id)
    assert not dispatch_event.called
    _bounty_check_state(b_id, False, False)

    _verdict_set(a_ids[0], 100)
    b.bounty_artifact_verdict(b_id)
    assert not dispatch_event.called
    _bounty_check_state(b_id, False, False)

    # Now it is complete
    _verdict_set(a_ids[1], 0)
    b.bounty_artifact_verdict(b_id)
    dispatch_event.assert_called_with("check_settle")
    _bounty_check_state(b_id, True, False)

    # Should not have an effect
    dispatch_event.reset_mock()
    b.bounty_artifact_verdict(b_id)
    assert not dispatch_event.called
    _bounty_check_state(b_id, True, False)

def test_fix_bitlist():
    assert fix_bitlist([], 0) == []
    assert fix_bitlist([True], 1) == [True]
    assert fix_bitlist([True], 2) == [True, False]
    assert fix_bitlist([True, False, True], 2) == [True, False]
