# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

# Application entry point

# TODO: VerdictSource => AnalysisBackend

from __future__ import print_function

import gevent
import logging
import os.path

from arbiter.backends import load_backends, analysis_backends
from arbiter.bounties import BountyComponent
from arbiter.events import Events, event_register_instance
from arbiter.monitor import MonitorComponent
from arbiter.polyswarm_api import PolySwarmAPI
from arbiter.verdicts import VerdictComponent, reset_pending_jobs
from arbiter.worker_api import APIComponent

from arbiter import ipfs

log = logging.getLogger(__name__)

class Arbiterd(object):
    """Start background components"""
    components = [
        APIComponent,
        Events,
        BountyComponent,
        VerdictComponent,
        MonitorComponent,
    ]

    def __init__(self, config):
        self.config = config
        self.host = config.host
        self.polyswarm = PolySwarmAPI(config.host, config.addr, config.password)
        # For dashboard
        self.wallet = {}

    def run(self):
        ipfs.ipfs_host = self.config.host
        ipfs.cache_path = self.config.artifacts

        reset_pending_jobs()

        load_backends(self.config.analysis_backends)
        log.debug("Analysis backends: %s", ", ".join(analysis_backends.keys()))
        if not analysis_backends:
            log.error("No analysis backends are available")
            raise ValueError("At least one analysis backend must be defined")

        if not os.path.exists(self.config.artifacts):
            log.info("Creating artifacts directory: %s",
                     self.config.artifacts)
            os.makedirs(self.config.artifacts)

        instances = []
        for c in self.components:
            log.debug("Create component %r", c.__name__)
            i = c(self)
            instances.append(i)
            event_register_instance(i)
        tasks = []
        for i in instances:
            log.debug("Run instance %r", i)
            tasks.append(gevent.spawn(trap_run, i.run))

        for t in tasks:
            t.join()

def trap_run(func):
    try:
        func()
    except:
        log.exception("Error in %r:", func)
