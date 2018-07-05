# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import gevent
import logging
import random

from arbiter.backends import analysis_backends
from arbiter.component import Component
from arbiter.dashboard import ui_broadcast_ws, ui_data_list, send
from arbiter.database import DbSession, DbBounty, DbArtifact
from arbiter.events import event, periodicx

log = logging.getLogger(__name__)

def broadcast(kind, data, remember=True):
    if remember:
        ui_data_list[kind] = data
    for c in ui_broadcast_ws:
        gevent.spawn(send, c, kind, data)

class MonitorComponent(Component):
    def __init__(self, parent):
        self.wallet = parent.wallet
        self.polyswarm = parent.polyswarm

    @event("block")
    def block(self, block_number):
        broadcast("counter-block", block_number)

    @event("bounty_manual")
    def bounty_manual(self, guid):
        # Tell WS clients to recheck pending bounties
        broadcast("bounties-updated", "manual", False)

    @event("bounty_settled")
    def bounty_settled(self, guid, value):
        broadcast("bounties-settled", {"guid": guid, "value": value}, False)

    @periodicx(minutes=5)
    def health_check(self):
        backends = {}
        for name, ab in analysis_backends.items():
            try:
                data = ab.health_check()
            except Exception as e:
                log.exception("Failed to perform health check on %s:", name)
                backends[name] = {"name": name, "error": str(e)}
                continue

            report = {"name": name, "error": False}
            if data:
                report.update(data)
            backends[name] = report

        broadcast("backends", backends)


    @periodicx(minutes=1)
    def update_wallet(self):
        nct = self.polyswarm.balance("nct")
        eth = self.polyswarm.balance("eth")
        wallet = {"addr": self.polyswarm.account,
                  "nct": nct,
                  "eth": eth}
        broadcast("wallet", wallet)

    @periodicx(seconds=30)
    def counters(self):
        # TODO: update on trigger
        counters = []
        s = DbSession()
        try:
            c = s.query(DbBounty.id).filter_by(truth_settled=True).count()
            counters.append(("counter-bounties-settled", c))

            c = s.query(DbArtifact.id).filter_by(processed=False).count()
            counters.append(("counter-artifacts-processing", c))

            counters.append(("counter-backends-running", len(analysis_backends)))
            counters.append(("counter-errors", random.randrange(0, 10)))
        finally:
            s.close()

        for k, c in counters:
            broadcast(k, c)
