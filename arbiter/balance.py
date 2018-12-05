# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import logging

from web3.auto import w3 as web3

from arbiter.component import Component
from arbiter.events import event, periodic, dispatch_event

log = logging.getLogger(__name__)

class BalanceComponent(Component):
    def __init__(self, parent):
        self.polyswarm = parent.polyswarm
        self.min_side = web3.toWei(100000000, "ether")
        self.refill_amount = self.min_side
        self.max_side = web3.toWei(250000000, "ether")
        self.min_block_wait = 600
        self.cur_block = None
        self.last_acted_block = None
        self.last_acted_block = None
        self.eth_balance = (None, None)
        self.nct_balance = (None, None)
        log.info(
            "Minimum balance: %s /  Maximum balance: %s",
            self.min_side, self.max_side)

    @event("block")
    def block_updated(self, block_number):
        self.cur_block = block_number

    @periodic(seconds=60)
    def balance_manager(self):
        if not self.cur_block:
            return
        if self.last_acted_block:
            blocks_passed = self.cur_block - self.last_acted_block
            if blocks_passed < self.min_block_wait:
                return

        eth_side = 0 #int(self.polyswarm.balance("eth", chain="side"))
        eth_home = int(self.polyswarm.balance("eth", chain="home"))
        eth = (eth_side, eth_home)
        if eth != self.eth_balance:
            log.debug("[ETH] Balance: %r / %r", eth_side, eth_home)
            self.eth_balance = eth

        nct_side = int(self.polyswarm.balance("nct", chain="side"))
        nct_home = int(self.polyswarm.balance("nct", chain="home"))
        nct = (nct_side, nct_home)
        if nct != self.nct_balance:
            log.debug("[NCT] Balance: %r / %r", nct_side, nct_home)
            self.nct_balance = nct

        dispatch_event("wallet_balance_info", nct, eth)

        if eth_home < 1000000000:
            log.error("Insufficient funds to relay transfer")
            return

        if nct_side < self.min_side:
            if self.refill_amount > nct_home:
                log.error(
                    "Insufficient funds on home chain to withdraw %s",
                    self.refill_amount)
            else:
                log.info(
                    "%s | Transferring %s from home to side",
                    self.cur_block, self.refill_amount)
                self.last_acted_block = self.cur_block
                self.polyswarm.relay_deposit(self.refill_amount, "home")

        elif nct_side > self.max_side:
            difference = nct_side - self.max_side
            log.info(
                "%s | Transferring %s from side to home",
                self.cur_block, difference)
            self.last_acted_block = self.cur_block
            self.polyswarm.relay_withdraw(difference, "side")
