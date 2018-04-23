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

from rarbiter.abstracts import Bounty, Address, EventQueue, Account

log = logging.getLogger(__name__)

class WebSocketListener(threading.Thread):
    def __init__(self, parent, uri):
        threading.Thread.__init__(self)
        self.queue = parent.queue
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
    def __init__(self, queue, config):
        threading.Thread.__init__(self)
        self.queue = queue
        self.config = config
        self.running = True

    def run(self):
        while self.running:
            bounty = self.queue.get()
            for contents in bounty.uri.fetch(self.config):
                log.debug(
                    "Fetched artifact with sha1: %s",
                    hashlib.sha1(contents).hexdigest()
                )

class PolySwarmd(object):
    def __init__(self, config):
        self.config = config
        self.host = config.host
        self.queue = EventQueue()
        self.samples_queue = queue.Queue()

        self.account = Account(config.addr, config.password)
        self.bf = self.ws = None
        self.running = True

    def init(self, start_threads=True):
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

    def handle_bounty(self, bounty, contents):
        # TODO Implement smarter decision!
        return random.randint(0, 1)

    def run(self):
        for bounty in self.queue.fetch_pending(self.host):
            self.samples_queue.put(bounty)

        while self.running:
            bounty = self.queue.get()
            if not bounty:
                time.sleep(1)
                continue

            log.info(
                "processing curblock=%d expiry=%d guid=%s resolved=%s",
                self.queue.cur_block, bounty.expiration, bounty.guid, bounty.resolved
            )

            verdicts = []
            for contents in bounty.uri.fetch(self.config):
                verdicts.append(bool(self.handle_bounty(bounty, contents)))

            if verdicts:
                log.debug("Settling %s => %s", bounty.guid, verdicts)
                bounty.settle(self.host, verdicts)
