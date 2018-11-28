# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import logging

from web3.auto import w3 as web3

from arbiter.component import Component
from arbiter.events import event, periodic

log = logging.getLogger(__name__)

class BalanceComponent(Component):
    def __init__(self, parent):
        self.polyswarm = parent.polyswarm
        self.buffer = web3.toWei(10000, "ether")
        self.min_side = web3.toWei(10000, "ether")
        self.max_side = web3.toWei(1000000, "ether")
        self.min_block_wait = 5
        self.cur_block = None
        self.last_acted_block = None

    @event("block")
    def block_updated(self, block_number):
        self.cur_block = block_number

    @periodic(seconds=10)
    def balance_manager(self):
        if not self.cur_block:
            return
        if self.last_acted_block:
            blocks_passed = self.cur_block - self.last_acted_block
            log.debug("Blocks passed: %s", blocks_passed)
            if blocks_passed < self.min_block_wait:
                return

        balance_side = int(self.polyswarm.balance("nct", chain="side"))
        balance_home = int(self.polyswarm.balance("nct", chain="home"))
        log.debug("Balance: %r / %r", balance_side, balance_home)

        if balance_side < self.min_side:
            difference = self.min_side - balance_side + self.buffer
            if difference > balance_home:
                log.error(
                    "Insufficient monies on home chain to withdraw %s",
                    difference)
            else:
                log.debug("Transferring %s from home to side", difference)
                self.last_acted_block = self.cur_block
                self.polyswarm.relay_deposit(difference, "home")

        elif balance_side >= self.max_side:
            difference = balance_side - self.max_side
            log.debug("Transferring %s from side to home", difference)
            self.last_acted_block = self.cur_block
            self.polyswarm.relay_withdraw(difference, "side")
