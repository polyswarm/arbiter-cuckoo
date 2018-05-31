# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import gevent
import random

from arbiter.backends import analysis_backends
from arbiter.component import Component
from arbiter.dashboard import ui_broadcast_ws, ui_data_list, send
from arbiter.database import DbSession, DbBounty, DbArtifact
from arbiter.events import periodicx

def broadcast(kind, data):
    ui_data_list[kind] = data
    for c in ui_broadcast_ws:
        gevent.spawn(send, c, kind, data)

class MonitorComponent(Component):
    def __init__(self, parent):
        self.wallet = parent.wallet
        self.polyswarm = parent.polyswarm

    @periodicx(minutes=1)
    def update_wallet(self):
        nct = self.polyswarm.balance("nct")
        eth = self.polyswarm.balance("eth")
        wallet = {"addr": self.polyswarm.account,
                  "nct": nct,
                  "eth": eth}
        broadcast("wallet", wallet)

    @periodicx(minutes=1)
    def update_backends(self):
        backends = {}
        for i, k in enumerate(analysis_backends.keys()):
            n = 1024 * (i + 2)
            backends[k] = {"name": k,
                           "cpu": random.randrange(0, 100),
                           "diskused": random.randrange(0, n*512),
                           "disktotal": n*512,
                           "memused": random.randrange(0, n),
                           "memtotal": n}
        broadcast("backends", backends)

    @periodicx(seconds=30)
    def counters(self):
        # TODO: update on trigger
        counters = []
        s = DbSession()
        try:
            c = s.query(DbBounty.id).filter_by(truth_settled=True).count()
            counters.append(("counter-bounties-settled", c))

            c = s.query(DbArtifact.id).filter(DbArtifact.verdict.is_(None)).count()
            counters.append(("counter-artifacts-processing", c))

            counters.append(("counter-backends-running", len(analysis_backends)))
            counters.append(("counter-errors", random.randrange(0, 10)))
        finally:
            s.close()

        for k, c in counters:
            broadcast(k, c)
