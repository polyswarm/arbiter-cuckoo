# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import logging
import requests
import six
import time

from gevent.lock import Semaphore
from gevent.subprocess import Popen, PIPE
from web3.auto import w3 as web3
from urllib.parse import quote
from json import dumps, loads, JSONDecodeError

log = logging.getLogger(__name__)

def _quote(v):
    if isinstance(v, bytes):
        v = v.encode("utf8")
    elif not isinstance(v, str):
        v = "%s" % v
    return quote(v)

def request_with_curl(method, url, params, headers, json):
    if params:
        url += "?" + "&".join("%s=%s" % (k, _quote(v)) for k, v in params.items())
    cmd = ["curl", "-s", "--connect-timeout", "3",
           "--max-time", "30", "-X", method, url]
    for kv in headers.items():
        cmd.extend(["-H", "%s: %s" % kv])
    if json:
        cmd.extend(["-H", "Content-Type: application/json; charset=utf8"])
        cmd.extend(["--data-raw", dumps(json)])
    #print(" ".join(('"' + c + '"') if ' ' in c else c for c in cmd))
    print(">>", cmd)
    p = Popen(cmd, stdout=PIPE)
    buf = b""
    while True:
        tmp = p.stdout.read(4096)
        if tmp == b"":
            break
        buf += tmp
    p.wait()
    print("<<", buf)
    if buf == b"":
        return {"errors": "no data returned (timeout?)", "status":"FAIL"}
    try:
        return loads(buf.decode("utf8"))
    except JSONDecodeError:
        return {"errors": str(buf), "status":"FAIL"}

class PolySwarmError(Exception):
    def __init__(self, status, message, reason=""):
        self.status = status
        self.message = message
        self.reason = reason

    def __str__(self):
        return "%s %s %s" % (self.status, self.message, self.reason)

class PolySwarmNotFound(PolySwarmError):
    pass

class DummyLock:
    def __enter__(self):
        return self

    def __exit__(self, typ, value, traceback):
        pass

class PolySwarmAPI(object):
    def __init__(self, config):
        #host, apikey, account, account_privkey,
        #         minimum_stake, chain):
        self.polyproxy = config.polyproxy
        self.host = config.polyswarmd
        self.apikey = config.apikey
        self.chain = config.chain
        self.minimum_stake = config.minimum_stake
        self.account_privkey = config.addr_privkey

        a = web3.eth.account.privateKeyToAccount(config.addr_privkey)
        self.account = a.address
        if config.addr and self.account != config.addr:
            log.warn("Oops, you didn't configure the correct public key!")
            raise ValueError((self.account, config.addr))
        log.info("Public key: %s", self.account)
        self.base_nonce = {"side": 0, "home": 0}
        self.base_nonce_lock = Semaphore()

        if self.polyproxy:
            self.lock = DummyLock()
        else:
            self.lock = Semaphore(64)

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
            {"chain": "home"}
        )

    def staking_balance_total(self):
        return self.balance("staking/total", chain="home")

    def staking_balance_withdrawable(self):
        return self.balance("staking/withdrawable", chain="home")

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
        func = getattr(requests, method)
        headers = {"Authorization": "Bearer %s" % self.apikey}
        params = params or {}
        params["account"] = self.account

        #_params = "&".join("%s=%s" % kv for kv in params.items())
        #log.debug("polyswarm: //%s/%s?%s", self.host, path, _params)
        #if body: log.debug("Payload: %r", body)

        addr = "https://%s/%s" % (self.host, path)
        kwargs = {"timeout": (10, 30)}
        if self.polyproxy:
            addr = "http://%s/%s" % (self.polyproxy, path)
            kwargs = {}

        resp = func(
            addr, json=body,
            params=params, headers=headers,
            **kwargs
        )

        status_code = resp.status_code
        if status_code == 404:
            raise PolySwarmNotFound(resp.status_code, resp.reason)
        try:
            r = resp.json()
        except ValueError:
            # XXX
            log.error("Invalid JSON! Status: %s Text: %s", resp.status_code, resp.text)
            raise PolySwarmError(resp.status_code, resp.reason)

        if r.get("status") != "OK":
            #msg = "%s: %s" % (r.get("status"), r.get("errors"))
            msg = str(r)
            raise PolySwarmError(status_code, msg)

        elif status_code < 200 or status_code > 299:
            # Error, but not explicit status?
            #log.error("Status: %s Text: %s", status_code, resp.text)
            raise PolySwarmError(status_code, "Bad status")

        return r.get("result")

    def req_and_sign(self, method, path, body=None, params=None):
        if self.polyproxy:
            return self(method, path, body, params)

        chain = self.chain
        chain = params.get("chain", chain)
        params = params or {}
        with self.base_nonce_lock:
            params["base_nonce"] = self.base_nonce[chain]
            self.base_nonce[chain] += 1  # Bad

        r = self(method, path, body, params)

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
            {"chain": chain}
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
