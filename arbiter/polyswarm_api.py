# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import logging
import random
import requests
import six
import time

from gevent.lock import Semaphore
from web3.auto import w3 as web3

log = logging.getLogger(__name__)

class PolySwarmError(Exception):
    def __init__(self, status, message, reason=''):
        self.status = status
        self.message = message
        self.reason = reason

    def __str__(self):
        return '%s %s %s' % (self.status, self.message, self.reason)

class PolySwarmNotFound(PolySwarmError):
    pass

class PolySwarmAPI(object):
    def __init__(self, host, apikey, account, account_privkey,
                 minimum_stake, chain="home"):
        self.host = host
        self.apikey = apikey
        self.account = account
        self.account_privkey = account_privkey
        self.chain = chain
        self.minimum_stake = minimum_stake
        self.base_nonce = 0
        self.base_nonce_lock = Semaphore()

    def wait_online(self, tries=30):
        for _ in range(tries):
            try:
                requests.get("https://%s/" % self.host, timeout=10)
                return
            except IOError:
                pass
            time.sleep(1)
        raise IOError("Polyswarm host at %s not line" % self.host)

    def set_base_nonce(self):
        with self.base_nonce_lock:
            self.base_nonce = self(requests.get, "/nonce")

    def set_windows(self):
        reveal = self(requests.get, "bounties/window/reveal")
        self.reveal_window = reveal["blocks"]
        log.info("Assertion reveal window: %s", self.reveal_window)

        vote = self(requests.get, "bounties/window/vote")
        self.vote_window = vote["blocks"]
        log.info("Vote window: %s", self.vote_window)

    def check_staking_requirements(self):
        staking_balance = int(self.staking_balance_total())

        if staking_balance < self.minimum_stake:
            raise PolySwarmError(
                "FATAL",
                "Insufficient funds staked! (minimum: %d, have: %d, need: %d)" % (
                    self.minimum_stake, staking_balance,
                    (self.minimum_stake - staking_balance)
                )
            )

    def balance(self, kind, account=None):
        if not account:
            account = self.account
        return self(requests.get, "balances/%s/%s" % (account, kind))

    def staking_deposit(self, amount):
        return self(
            requests.post, "staking/deposit",
            {"amount": str(amount)}, sign=True
        )

    def staking_balance_total(self):
        return self.balance("staking/total")

    def staking_balance_withdrawable(self):
        return self.balance("staking/withdrawable")

    def bounty(self, guid):
        return self(requests.get, "bounties/%s" % guid)

    def pending_bounties(self):
        b = self(requests.get, "bounties/pending")
        b.extend(self(requests.get, "bounties/active"))
        return b

    def bounty_assertions(self, guid):
        return self(requests.get, "bounties/%s/assertions" % guid)

    def vote_bounty(self, guid, verdicts):
        args = (guid, self.chain)
        self(
            requests.post, "bounties/%s/vote?chain=%s" % args,
            {"verdicts": verdicts, "valid_bloom": False},
            sign=True
        )

    def settle_bounty(self, guid):
        args = (guid, self.chain)
        self(
            requests.post, "bounties/%s/settle&chain=%s" % args,
            sign=True
        )

    def __call__(self, method, path, args=None, sign=False):
        headers = {}
        if self.apikey:
            headers = {
                "Authorization": "Bearer %s" % self.apikey,
            }
        else:
            if "?" in path:
                path += "&account=%040x" % self.account
            else:
                path += "?account=%040x" % self.account

        # Release base nonce lock if acquired at end of this block
        try:
            if sign:
                self.base_nonce_lock.acquire()
                if "?" in path:
                    path += "&base_nonce=%s" % self.base_nonce
                else:
                    path += "?base_nonce=%s" % self.base_nonce

            resp = method(
                "https://%s/%s" % (self.host, path), json=args,
                headers=headers, timeout=120
            )
            try:
                r = resp.json()
            except ValueError:
                if resp.status_code == 404:
                    raise ValueError("404 on %s" % path)
            if resp.status_code == 404:
                raise PolySwarmNotFound(resp.status_code, r.get("status"), resp.reason)
            elif resp.status_code != 200:
                raise PolySwarmError(resp.status_code, r.get("message"), resp.reason)
            if r.get("status") != "OK":
                raise PolySwarmError(resp.status_code, r.get("status"))
            r = r.get("result")
            if sign:
                signed = []
                txs = r.get("transactions", [])
                for tx in txs:
                    s = web3.eth.account.signTransaction(tx, self.account_privkey)
                    signed.append(bytes(s["rawTransaction"]).hex())

                self.base_nonce += len(txs)
        finally:
            if self.base_nonce_lock.locked():
                self.base_nonce_lock.release()

        if sign:
            # TODO Error checking - did the transaction succeed?
            return self(requests.post, "transactions", {"transactions": signed})

        return r

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
