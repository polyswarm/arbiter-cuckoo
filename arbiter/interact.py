# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import hashlib
import json
import logging
import os
import queue
import random
import threading
import time
import websocket

from sqlalchemy import func

from arbiter.abstracts import Bounty, BountyVerdict, Address, EventQueue, Account
from arbiter.database import DbSession, DbBounty, DbVerdict, DbArtifact
from arbiter.sources import load_sources, verdict_sources
from arbiter.const import VERDICT_MALICIOUS

log = logging.getLogger(__name__)

class WebSocketListener(threading.Thread):
    def __init__(self, parent, uri):
        threading.Thread.__init__(self)
        self.queue = parent.event_queue
        self.samples_queue = parent.samples_queue
        self.uri = uri

    def on_message(self, ws, message):
        obj = json.loads(message)
        if obj["event"] == "bounty":
            bounty = self.queue.push_bounty(obj["data"])
            self.samples_queue.put(bounty)
        if obj["event"] == "block":
            self.queue.push_block(obj["data"]["number"])
        if obj["event"] == "assertion":
            self.queue.push_assertion(obj["data"])
        if obj["event"] == "verdict":
            self.queue.push_verdict(obj["data"])

    def run(self):
        ws = websocket.WebSocketApp(self.uri, on_message=self.on_message)
        ws.run_forever()

class BinaryFetcher(threading.Thread):
    """
    Fetch & submit
    """
    def __init__(self, queue, config):
        threading.Thread.__init__(self)
        self.queue = queue
        self.config = config
        self.running = True

    def run(self):
        while self.running:
            bounty = self.queue.get()
            # TODO: fix this API/names
            for contents in bounty.uri.fetch(self.config):
                if contents is None:
                    continue

                log.debug(
                    "Fetched artifact with sha1: %s",
                    hashlib.sha1(contents).hexdigest()
                )

            for artifact in bounty.uri.artifacts:
                self.submit_for_verdict(artifact)

    def submit_for_verdict(self, artifact):
        for s in verdict_sources.values():
            try:
                log.debug("Submit artifact #%s to %s", artifact.id, s.name)
                s.submit_artifact(artifact)
            except:
                log.exception("Failed to submit artifact to %s", s.name)

class ApiContainer(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        from arbiter.worker_api import app
        app.run()

class VerdictChecker(threading.Thread):
    def __init__(self, host, config, expect_verdicts):
        threading.Thread.__init__(self)
        self.config = config
        self.running = True
        self.db = DbSession()
        self.host = host
        self.expect_verdicts = expect_verdicts

    def run(self):
        while self.running:
            # TODO: implement an event API, or at least wait until there
            # was activity in the relevant API function
            for bounty in self.db.query(DbBounty).filter_by(settled=0):
                qa = self.db.query(DbArtifact).filter_by(
                    bounty_id=bounty.id
                ).order_by(DbArtifact.id.asc())

                artifact_cnt = qa.count()
                artifact_verdicts = []

                if artifact_cnt:
                    log.info("Artifacts for bounty %s: %s", bounty.guid,
                             artifact_cnt)

                for artifact in qa:
                    # TODO: we should store the "final" verdict related
                    # to the artifact
                    # TODO: we could just get the counts with a group_by

                    verdicts = self.db.query(DbVerdict.verdict_value,
                                             func.count(1)) \
                        .group_by(DbVerdict.verdict_value) \
                        .filter_by(artifact_id=artifact.id).all()

                    total = 0
                    malicious = 0
                    for v in verdicts:
                        # TODO: we don't do anything with all the other
                        # potential verdict values yet
                        if v[0] is VERDICT_MALICIOUS:
                            malicious += 1
                        total += v[1]

                    # At least one malintent means final verdict for artifact
                    if malicious > 0:
                        log.info("Verdict: malicious (%s source(s) said so)",
                                 malicious)
                        artifact_verdicts.append(True)

                    elif total >= self.expect_verdicts:
                        # Everyone says benign? final verdict
                        log.info("Verdict: safe (%s source(s) said so)",
                                 total)
                        artifact_verdicts.append(False)

                # Do we have final verdicts for every artifact in bounty?
                # Settle!
                if artifact_verdicts and len(artifact_verdicts) == artifact_cnt:
                    log.info(
                        "Final verdict for every artifact in bounty %s " +
                        "reached! %s settling..",
                        bounty.guid, artifact_verdicts
                    )

                    # TODO: we don't need to store the bounty, especially
                    # if we don't store the final verdict

                    bounty_verdict = BountyVerdict(bounty.guid)
                    bounty_verdict.settle(self.host, artifact_verdicts)

                    db_bounty = self.db.query(DbBounty).filter_by(
                        guid=bounty.guid
                    ).first()

                    db_bounty.settled = 1
                    self.db.commit()

            time.sleep(10)

class PolySwarmd(object):
    def __init__(self, config):
        self.config = config
        self.host = config.host
        self.event_queue = EventQueue()
        self.samples_queue = queue.Queue()
        self.db = DbSession()

        self.account = Account(config.addr, config.password)
        self.bf = self.ws = None
        self.running = True

    def init(self, start_threads=True):
        load_sources(self.config.verdict_sources)
        log.debug("Verdict sources: %s", ", ".join(verdict_sources.keys()))
        if not verdict_sources:
            log.error("No verdict sources are available")
            raise ValueError("At least one verdict source must be defined")

        self.account.unlock(self.host)

        if not os.path.exists(self.config.artifacts):
            log.info(
                "Creating artifacts directory: %s", self.config.artifacts
            )
            os.mkdir(self.config.artifacts)

        self.bf = BinaryFetcher(self.samples_queue, self.config)
        self.bf.daemon = True
        start_threads and self.bf.start()

        self.ws = WebSocketListener(self, "ws://%s/events" % self.host)
        self.ws.daemon = True
        start_threads and self.ws.start()

        self.ac = ApiContainer()
        self.ac.daemon = True
        start_threads and self.ac.start()

        self.vc = VerdictChecker(self.host, self.config, len(verdict_sources))
        self.vc.daemon = True

    def handle_bounty(self, bounty, contents):
        # TODO Implement smarter decision!
        return random.randint(0, 1)

    def run(self):
        for bounty in self.event_queue.fetch_pending(self.host):
            self.samples_queue.put(bounty)

        self.vc.start()

        while self.running:
            bounty = self.event_queue.get()

            if not bounty:
                time.sleep(1)
                continue

            log.info(
                "processing curblock=%d expiry=%d guid=%s resolved=%s",
                self.event_queue.cur_block, bounty.expiration,
                bounty.guid, bounty.resolved
            )

            bounty.uri.fetch(self.config)
