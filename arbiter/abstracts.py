# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import collections
import json
import logging
import os
import requests
import six

log = logging.getLogger(__name__)

class Account(object):
    def __init__(self, addr, password):
        self.addr = Address(addr)
        self.password = password

    def unlock(self, host):
        r = requests.post(
            "http://%s/accounts/%s/unlock" % (host, self.addr),
            json={
                "password": self.password,
            }
        )
        r.raise_for_status()

class Address(object):
    def __init__(self, addr):
        if isinstance(addr, six.string_types):
            self.addr = int(addr, 16)
        else:
            self.addr = addr

    def __cmp__(self, other):
        if isinstance(other, Address):
            other = other.addr
        return self.addr != other

    def __eq__(self, other):
        return not self.__cmp__(other)

    def __str__(self):
        if isinstance(self.addr, six.integer_types):
            return "0x%040x" % self.addr
        return self.addr

class Artifact(object):
    def __init__(self, uri):
        self.uri = uri

    def fetch(self, config):
        cache_path = os.path.join(config.artifacts, self.uri)
        if not os.path.exists(cache_path):
            log.debug("Fetching ipfs listing: %s", self.uri)
            r = requests.get(
                "http://%s/artifacts/%s" % (config.host, self.uri)
            )

            cache_path = os.path.join(config.artifacts, self.uri)
            open(cache_path, "wb").write(json.dumps(r.json()))

        manifest = json.loads(open(cache_path, "rb").read().decode())
        for idx, value in enumerate(manifest.get("result", [])):
            cache_path = os.path.join(config.artifacts, value)
            if not os.path.exists(cache_path):
                log.debug("Fetching ipfs hash: %s %d", self.uri, idx)
                open(cache_path, "wb").write(requests.get(
                    "http://%s/artifacts/%s/%d" % (config.host, self.uri, idx)
                ).content)

            yield open(cache_path, "rb").read()

    def __cmp__(self, other):
        if isinstance(other, Artifact):
            other = other.uri
        return self.uri != other

    def __eq__(self, other):
        return not self.__cmp__(other)

class Assertion(object):
    def __init__(self, guid=None, author=None, index=None, bid=None,
                 mask=None, metadata=None, verdicts=None):
        self.guid = guid
        self.author = author
        self.index = index
        self.bid = bid
        self.mask = mask
        self.metadata = metadata
        self.verdicts = verdicts

    @staticmethod
    def from_dict(d):
        return Assertion(
            guid=d.get("bounty_guid"),
            author=Address(d["author"]),
            index=d.get("index"),
            bid=int(d["bid"]),
            mask=d["mask"],
            metadata=d["metadata"],
            verdicts=d["verdicts"]
        )

    def __cmp__(self, other):
        return not (
            self.guid == other.guid and
            self.author == other.author and
            self.index == other.index and
            self.bid == other.bid and
            self.mask == other.mask and
            self.metadata == other.metadata and
            self.verdicts == other.verdicts
        )

    def __eq__(self, other):
        return not self.__cmp__(other)

class Verdict(object):
    def __init__(self, guid=None, verdicts=None):
        self.guid = guid
        self.verdicts = verdicts

    @staticmethod
    def from_dict(d):
        return Verdict(
            guid=d["bounty_guid"],
            verdicts=d["verdicts"],
        )

    def __cmp__(self, other):
        return not (
            self.guid == other.guid and
            self.verdicts == other.verdicts
        )

    def __eq__(self, other):
        return not self.__cmp__(other)

class Bounty(object):
    def __init__(self, amount=None, author=None, expiration=None, guid=None,
                 resolved=None, uri=None, verdicts=None, assertions=None):
        self.amount = amount
        self.author = author
        self.expiration = expiration
        self.guid = guid
        self.resolved = resolved
        self.uri = uri
        self.verdicts = verdicts

        self.assertions = [] if assertions is None else assertions

    @staticmethod
    def from_dict(d):
        return Bounty(
            amount=int(d["amount"]),
            author=Address(d["author"]),
            expiration=int(d["expiration"]),
            guid=d["guid"],
            resolved=d.get("resolved"),
            uri=Artifact(d["uri"]),
            verdicts=d.get("verdicts"),
        )

    def fetch_assertions(self, host):
        r = requests.get(
            "http://%s/bounties/%s/assertions" % (host, self.guid)
        )
        for idx, entry in enumerate(r.json()["result"]):
            entry["index"] = idx
            yield Assertion.from_dict(entry)

    def settle(self, host, verdicts):
        r = requests.post(
            "http://%s/bounties/%s/settle" % (host, self.guid), json={
                "verdicts": verdicts,
            }
        )
        r.raise_for_status()

    def __cmp__(self, other):
        return not (
            self.amount == other.amount and
            self.author == other.author and
            self.expiration == other.expiration and
            self.guid == other.guid and
            self.resolved == other.resolved and
            self.uri == other.uri and
            self.verdicts == other.verdicts and
            self.assertions == other.assertions
        )

    def __eq__(self, other):
        return not self.__cmp__(other)

class EventQueue(object):
    def __init__(self):
        # guid => bounty
        self.bounties = {}
        # block number => bounties
        self.expiration = collections.defaultdict(list)

        # Only used during early initialization.
        # guid => assertions
        self.assertions = collections.defaultdict(list)

        self.last_block = None
        self.cur_block = None

    def fetch_pending(self, host):
        r = requests.get("http://%s/bounties" % host)
        r.raise_for_status()

        for entry in r.json()["result"]:
            bounty = self.push_bounty(entry)

            if bounty.resolved is not True:
                for assertion in bounty.fetch_assertions(host):
                    assertion.guid = bounty.guid
                    bounty.assertions.append(assertion)

            yield bounty

    def push_bounty(self, bounty):
        bounty = Bounty.from_dict(bounty)

        for assertion in self.assertions.pop(bounty.guid, []):
            # TODO Assertion already included?
            bounty.assertions.append(assertion)

        # If the expiration of this bounty is lower than self.cur_block, then
        # lower the self.cur_block once again. TODO Unit test.
        if self.cur_block and bounty.expiration < self.cur_block:
            self.cur_block = block.expiration

        if bounty.resolved is False:
            self.expiration[bounty.expiration].append(bounty)

        self.bounties[bounty.guid] = bounty
        return bounty

    def push_assertion(self, assertion):
        if not isinstance(assertion, Assertion):
            assertion = Assertion.from_dict(assertion)

        # This will only happen during initialization.
        if assertion.guid not in self.bounties:
            self.assertions[assertion.guid].append(assertion)
            return

        self.bounties[assertion.guid].assertions.append(assertion)

    def push_verdict(self, verdict):
        verdict = Verdict.from_dict(verdict)
        log.debug(
            "Noticed verdict guid=%s verdicts=%s",
            verdict.guid, verdict.verdicts
        )

    def push_block(self, number):
        self.last_block = number

    def get(self):
        if not self.expiration or not self.last_block:
            return

        if self.cur_block is None:
            self.cur_block = min(self.expiration.keys())

        # Locate next expiration block.
        while self.cur_block < self.last_block:
            if self.expiration.get(self.cur_block):
                break
            self.cur_block += 1

        try:
            return self.expiration[self.cur_block].pop(0)
        except IndexError:
            pass
