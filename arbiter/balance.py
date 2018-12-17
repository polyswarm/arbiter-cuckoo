# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import logging

from web3.auto import w3 as web3

from arbiter.component import Component
from arbiter.events import event, periodic, periodicx, dispatch_event

log = logging.getLogger(__name__)

def val_readable(wei, unit=None):
    if unit == "nct":
        # decimals = 18, so this works out
        pass
    v = web3.fromWei(wei, "ether")
    return str(v) + ((" " + unit) if unit else "")

class BalanceComponent(Component):
    def __init__(self, parent):
        self.polyswarm = parent.polyswarm
        self.min_side = web3.toWei(100000000, "ether")
        self.refill_amount = self.min_side
        self.max_side = web3.toWei(250000000, "ether")
        # At least 5 minutes
        self.min_block_wait = 330
        self.cur_block = parent.initial_block
        self.wait_until_block = None
        # (side, home)
        self.eth_balance = (None, None)
        self.nct_balance = (None, None)
        self.changed = False
        log.info(
            "Minimum balance: %s /  Maximum balance: %s",
            self.min_side, self.max_side)

    @event("block")
    def block_updated(self, block_number):
        self.cur_block = block_number

    @periodicx(seconds=60)
    def check_balance(self):
        eth_side = 0 #int(self.polyswarm.balance("eth", chain="side"))
        eth_home = int(self.polyswarm.balance("eth", chain="home"))
        eth = (eth_side, eth_home)
        if eth != self.eth_balance:
            log.debug("[ETH] Balance: %s", val_readable(eth_home, "eth"))
            self.eth_balance = eth
            self.changed = True

        nct_side = int(self.polyswarm.balance("nct", chain="side"))
        nct_home = int(self.polyswarm.balance("nct", chain="home"))
        nct = (nct_side, nct_home)
        if nct != self.nct_balance:
            log.debug("[NCT] Balance: %s / %s", val_readable(nct_side, "nct"),
                val_readable(nct_home, "nct"))
            self.nct_balance = nct
            self.changed = True

        dispatch_event("wallet_balance_info", nct, eth)

    @periodic(seconds=121)
    def balance_manager(self):
        if self.wait_until_block is not None:
            # Always wait until something changed
            if not self.changed:
                return
            if self.cur_block < self.wait_until_block:
                return
            self.wait_until_block = None

        eth = self.eth_balance
        if eth[1] < 1000000000:
            log.error("Insufficient funds to relay transfer")
            return

        self.changed = False
        nct = self.nct_balance
        if nct[0] < self.min_side:
            if self.refill_amount > nct[1]:
                log.error(
                    "Insufficient funds on home chain to withdraw %s",
                    self.refill_amount)
            else:
                log.info(
                    "%s | Transferring %s from home to side",
                    self.cur_block, val_readable(self.refill_amount, "nct"))
                self.wait_until_block = self.cur_block + self.min_block_wait
                self.polyswarm.relay_deposit(self.refill_amount, "home")

        elif nct[0] > self.max_side:
            difference = nct[0] - self.max_side
            log.info(
                "%s | Transferring %s from side to home",
                self.cur_block, val_readable(difference, "nct"))
            self.wait_until_block = self.cur_block + self.min_block_wait
            self.polyswarm.relay_withdraw(difference, "side")
