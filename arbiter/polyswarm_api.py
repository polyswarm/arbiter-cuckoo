# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import logging
import requests
import six
import time

from gevent.lock import Semaphore
from web3.auto import w3 as web3

log = logging.getLogger(__name__)

class PolySwarmError(Exception):
    def __init__(self, status, message, reason=""):
        self.status = status
        self.message = message
        self.reason = reason

    def __str__(self):
        return "%s %s %s" % (self.status, self.message, self.reason)

class PolySwarmNotFound(PolySwarmError):
    pass

class PolySwarmAPI(object):
    def __init__(self, host, apikey, account, account_privkey,
                 minimum_stake, chain):
        self.host = host
        self.apikey = apikey
        self.account_privkey = account_privkey
        a = web3.eth.account.privateKeyToAccount(account_privkey)
        self.account = a.address
        if account:
            if self.account != account:
                log.warn("Oops, you didn't configure the correct public key!")
                raise ValueError((self.account, account))
        log.info("Public key: %s", self.account)
        self.chain = chain
        self.minimum_stake = minimum_stake
        self.base_nonce = {"side": 0, "home": 0}
        self.base_nonce_lock = Semaphore()
        self.api_concurrent = Semaphore(8)
        #self.session = requests.Session()

    def wait_online(self, tries=30):
        for _ in range(tries):
            try:
                s = self.status()
                return s.get("side", {}).get("block")
            except IOError:
                s = None
            time.sleep(1)
        raise IOError("Polyswarm host at %s not online" % self.host)

    def status(self):
        return self("get", "status")

    def set_base_nonce(self):
        with self.base_nonce_lock:
            side = self("get", "nonce", params={"chain": "side"})
            home = self("get", "nonce", params={"chain": "home"})
            self.base_nonce = {"side": side, "home": home}
            log.info("Base nonce: %s", self.base_nonce)

    def nonce_sync(self):
        with self.base_nonce_lock:
            # XXX: this may not work.
            side = self("get", "nonce", params={"chain": "side"})
            home = self("get", "nonce", params={"chain": "home"})
            if side > self.base_nonce["side"]:
                self.base_nonce["side"] = side
                log.error("Side nonce forwarded: %s", side)
            if home > self.base_nonce["home"]:
                self.base_nonce["home"] = home
                log.error("Home nonce forwarded: %s", side)

    def set_params(self):
        params = self("get", "bounties/parameters")
        self.reveal_window = params["assertion_reveal_window"]
        log.info("Assertion reveal window: %s", self.reveal_window)
        self.vote_window = params["arbiter_vote_window"]
        log.info("Vote window: %s", self.vote_window)

    def check_staking_requirements(self):
        staking_balance = int(self.staking_balance_total())

        if staking_balance < self.minimum_stake:
            raise PolySwarmError(
                "FATAL",
                "Insufficient funds staked! (minimum: %d, have: %d, need: %d)"
                % (
                    self.minimum_stake, staking_balance,
                    (self.minimum_stake - staking_balance)
                )
            )

    def balance(self, kind, account=None, chain=None):
        if not account:
            account = self.account
        p = None
        if chain:
            p = {"chain": chain}
        return self("get", "balances/%s/%s" % (account, kind), params=p)

    def staking_deposit(self, amount):
        return self.req_and_sign(
            "post", "staking/deposit",
            {"amount": str(amount)},
            {"chain": self.chain}
        )

    def staking_balance_total(self):
        return self.balance("staking/total", chain=self.chain)

    def staking_balance_withdrawable(self):
        return self.balance("staking/withdrawable", chain=self.chain)

    def bounty(self, guid):
        return self("get", "bounties/%s" % guid)

    def pending_bounties(self):
        b = self("get", "bounties/pending")
        b.extend(self("get", "bounties/active"))
        return b

    def bounty_assertions(self, guid):
        return self("get", "bounties/%s/assertions" % guid)

    def vote_bounty(self, guid, votes):
        self.req_and_sign(
            "post", "bounties/%s/vote" % guid,
            {"votes": votes, "valid_bloom": False},
            params={"chain": self.chain}
        )

    def settle_bounty(self, guid):
        self.req_and_sign(
            "post", "bounties/%s/settle" % guid,
            params={"chain": self.chain}
        )

    def relay_withdraw(self, amount, chain):
        return self.req_and_sign(
            "post", "relay/withdrawal",
            {"amount": str(amount)},
            {"chain": chain}
        )

    def relay_deposit(self, amount, chain):
        return self.req_and_sign(
            "post", "relay/deposit",
            {"amount": str(amount)},
            {"chain": chain}
        )

    def __call__(self, method, path, body=None, params=None, session=None):
        if not session:
            session = requests.Session()
        func = getattr(session, method)
        #func = getattr(self.session, method)
        headers = {"Authorization": "Bearer %s" % self.apikey}
        params = params or {}
        params["account"] = self.account

        #_params = "&".join("%s=%s" % kv for kv in params.items())
        #log.debug("polyswarm: //%s/%s?%s", self.host, path, _params)
        #if body: log.debug("Payload: %r", body)

        resp = func(
            "https://%s/%s" % (self.host, path), json=body,
            params=params, headers=headers, timeout=(10, 30)
        )

        if resp.status_code == 404:
            raise PolySwarmNotFound(resp.status_code, resp.reason)
        try:
            r = resp.json()
        except ValueError:
            # XXX
            log.error("Invalid JSON! Status: %s Text: %s", resp.status_code, resp.text)
            raise PolySwarmError(resp.status_code, resp.reason)

        if r.get("status") != "OK":
            msg = "%s: %s" % (r.get("status"), r.get("errors"))
            raise PolySwarmError(resp.status_code, msg)

        elif resp.status_code < 200 or resp.status_code > 299:
            # Error, but not explicit status?
            log.error("Status: %s Text: %s", resp.status_code, resp.text)
            raise PolySwarmError(resp.status_code, resp.reason)

        return r.get("result")

    def req_and_sign(self, method, path, body=None, params=None):
        chain = self.chain
        chain = params.get("chain", chain)
        params = params or {}
        with self.base_nonce_lock:
            params["base_nonce"] = self.base_nonce[chain]
            self.base_nonce[chain] += 1  # Bad

        reqses = requests.Session()
        with self.api_concurrent:
            r = self(method, path, body, params, session=reqses)

        signed, transactions = [], r.get("transactions", [])
        if len(transactions) != 1:
            log.error("Oops, we broke the nonce! %s %s", path, len(transactions))
            diff = len(transactions) - 1
            if diff > 0:
                # At least try to unbreak
                with self.base_nonce_lock:
                    self.base_nonce[chain] += diff

        for transaction in transactions:
            s = web3.eth.account.signTransaction(
                transaction, self.account_privkey
            )
            signed.append(bytes(s["rawTransaction"]).hex())

        r = self(
            "post", "transactions",
            {"transactions": signed},
            {"chain": chain},
            session=reqses
        )
        if not r:
            log.error("Potential transaction error")
        elif r.get("errors"):
            raise PolySwarmError(500, "\n".join(r["errors"]))
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
