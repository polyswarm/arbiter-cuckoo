# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

from requests import get, post
import six

class PolySwarmError(Exception):
    def __init__(self, status, message, reason=''):
        self.status = status
        self.message = message
        self.reason = reason

    def __str__(self):
        return '%s %s %s' % (self.status, self.message, self.reason)

class PolySwarmAPI:
    def __init__(self, host, account, password):
        self.host = host
        self.account = account
        self.password = password

    def account_unlock(self):
        return self(post, "accounts/%s/unlock" % self.account,
                    {"password": self.password})

    def balance(self, kind, account=None):
        if not account:
            account = self.account
        return self(get, "accounts/%s/balance/%s" % (account, kind))

    def pending_bounties(self):
        b = self(get, "bounties/pending")
        b.extend(self(get, "bounties/active"))
        return b

    def bounty_assertions(self, guid):
        return self(get, "bounties/%s/assertions" % guid)

    def settle_bounty(self, guid, verdicts):
        return self(post, "bounties/%s/settle" % guid, {"verdicts": verdicts})

    def __call__(self, method, path, args=None):
        resp = method("http://%s/%s" % (self.host, path), json=args)
        r = resp.json()
        if resp.status_code != 200:
            raise PolySwarmError(resp.status_code, r.get("status"), resp.reason)
        if r.get("status") != "OK":
            raise PolySwarmError(resp.status_code, r.get("status"))
        return r.get("result")

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
            uri=d["uri"],
            verdicts=d.get("verdicts"),
        )

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
