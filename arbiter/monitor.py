# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import gevent
import logging
import time

from arbiter.backends import analysis_backends
from arbiter.component import Component
from arbiter.dashboard import ui_broadcast_ws, ui_data_list, send
from arbiter.database import DbSession, DbBounty, DbArtifact
from arbiter.events import event, periodic, periodicx

log = logging.getLogger(__name__)

def broadcast(kind, data, remember=True):
    if remember:
        ui_data_list[kind] = data
    for c in ui_broadcast_ws:
        gevent.spawn(send, c, kind, data)

class PrometheusMonitor:
    def __init__(self):
        self.level = logging.ERROR  # Terrible hack
        self.metrics = {"arbiter_errors": 0,
                        "arbiter_jobs_submitted": 0,
                        "polyswarm_settled": 0,
                        "arbiter_artifacts_completed": 0}
        self.errors = 0

    def server(self, bind):
        self.track("arbiter_started", int(time.time()))
        host, port = bind.split(":")
        gevent.pywsgi.WSGIServer((host, int(port)), self).serve_forever()

    def handle(self, record):
        if record.levelno >= logging.ERROR:
            self.errors += 1
            self.track("arbiter_errors", self.errors)

    def track(self, key, value):
        self.metrics[key] = value

    def count(self, key, n=1):
        self.metrics[key] = self.metrics.get(key, 0) + n

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO") != "/probe":
            start_response("404 Not Found", [])
            return []
        start_response("200 OK", [("Content-Type", "text/plain")])
        r = ""
        for k, v in self.metrics.items():
            r += "%s %s\n" % (k, v)
        return [r.encode("utf8")]

class MonitorComponent(Component):
    def __init__(self, parent):
        self.wallet = parent.wallet
        self.polyswarm = parent.polyswarm

        self.metrics = PrometheusMonitor()
        logging.getLogger().addHandler(self.metrics)
        gevent.spawn(self.metrics.server, parent.config.monitor_bind)

        # We keep track of the starting time of polyswarmd such that we can
        # reset (i.e., early exit) the Arbiter if we're in testing mode (i.e.,
        # the Polyswarm end-to-end testing environment).
        self.testing_mode = parent.config.testing_mode
        self.start_time = None

    @event("block")
    def block(self, block_number):
        broadcast("counter-block", block_number)
        self.metrics.track("polyswarm_block", block_number)

    @event("connected")
    def connected(self, data):
        if self.start_time is None:
            self.start_time = data["start_time"]

        if self.testing_mode and self.start_time != data["start_time"]:
            log.info(
                "Exiting Arbiter as a new Hive end-to-end testing "
                "environment has been identified."
            )
            exit(0)

    @event("metrics_jobs_submitted")
    def metrics_jobs_submitted(self, num_jobs):
        self.metrics.count("arbiter_jobs_submitted", num_jobs)

    @event("metrics_artifact_complete")
    def metrics_artifact_complete(self, num_artifacts):
        self.metrics.count("arbiter_artifacts_completed", )

    @event("bounty_manual")
    def bounty_manual(self, guid):
        # Tell WS clients to recheck pending bounties
        broadcast("bounties-updated", "manual", False)

    @event("bounty_voted")
    def bounty_voted(self, guid, value):
        broadcast("bounties-voted", {"guid": guid, "value": value}, False)
        self.metrics.count("arbiter_voted")

    @event("bounty_settled")
    def bounty_settled(self, guid):
        broadcast("bounties-settled", {"guid": guid}, False)
        #self.metrics.count("arbiter_settled")

    @event("polyswarm_bounty_settled")
    def polyswarm_bounty_settled(self, guid):
        self.metrics.count("polyswarm_settled")

    @periodic(minutes=1)
    def nonce_check(self):
        self.polyswarm.nonce_sync()

    @periodicx(minutes=5)
    def health_check(self):
        backends = {}
        for name, ab in analysis_backends.items():
            try:
                data = ab.health_check()
            except Exception as e:
                log.error("Failed to perform health check on %s: %s", name, e)
                backends[name] = {"name": name, "error": str(e)}
                continue

            report = {"name": name, "error": False}
            if data:
                report.update(data)
            backends[name] = report

        broadcast("backends", backends)

    @event("wallet_balance_info")
    def wallet_balance_info(self, nct, eth):
        # Home chain values
        wallet = {"addr": self.polyswarm.account,
                  "nct": nct[1],
                  "eth": eth[1]}
        broadcast("wallet", wallet)

    @periodicx(seconds=30)
    def counters(self):
        # TODO: update on trigger
        counters = []
        s = DbSession()
        try:
            c = s.query(DbBounty.id).filter_by(settled=True).count()
            counters.append(("counter-bounties-settled", c))

            c = s.query(DbArtifact.id).filter_by(processed=False).count()
            counters.append(("counter-artifacts-processing", c))

            counters.append(("counter-backends-running", len(analysis_backends)))
            counters.append(("counter-errors", 0))
        finally:
            s.close()

        for k, c in counters:
            broadcast(k, c)
