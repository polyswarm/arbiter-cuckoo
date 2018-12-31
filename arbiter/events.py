# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

# TODO: better name for this module

import datetime
import gevent
import json
import logging
import socket

from ws4py.client import geventclient

from arbiter.component import Component

log = logging.getLogger(__name__)

class Events(Component):
    def __init__(self, parent):
        self.polyswarm = parent.polyswarm
        self.uri = "wss://%s/events?chain=%s" % (
            parent.config.polyswarmd,
            parent.config.chain
        )
        self.account = parent.polyswarm.account.lower()

    def on_message(self, message):
        obj = json.loads(message)

        if obj["event"] == "bounty":
            # TODO Fetching additional bounty information from polyswarmd
            # is done primarily for checking num_artifacts. Should we
            # reintroduce this? For now doesn't seem 100% necessary.
            # bounty = self.polyswarm.bounty(obj["data"]["guid"])
            dispatch_event("bounty", obj["data"])

        elif obj["event"] == "block":
            dispatch_event("block", obj["data"]["number"])

        elif obj["event"] == "assertion":
            dispatch_event("assertion", obj["data"])

        elif obj["event"] == "vote":
            # XXX unused
            dispatch_event("vote", obj["data"])

        elif obj["event"] == "connected":
            dispatch_event("connected", obj["data"])

        elif obj["event"] == "reveal":
            # TODO
            pass

        elif obj["event"] == "quorum":
            pass

        elif obj["event"] == "settled_bounty":
            data = obj["data"]
            if self.account == data["settler"].lower():
                dispatch_event("polyswarm_bounty_settled", data["bounty_guid"])
        else:
            log.debug("Unhandled event: %r", obj)

    def run(self):
        while True:
            ws = geventclient.WebSocketClient(self.uri)
            log.info("Connecting to %s", self.uri)
            try:
                ws.connect()
                ws.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                ws.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
                ws.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                ws.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)

                log.debug("Connected")
                self.pending_bounties()
                while True:
                    m = ws.receive()
                    if m is None:
                        break
                    self.on_message(m.data)
            except socket.error as e:
                log.error("Events.run: %s", e)
            except:
                log.exception("Events.run")
            try:
                ws.close()
            except:
                pass
            log.info("Disconnected")
            gevent.sleep(3)

    def pending_bounties(self):
        # for bounty in self.polyswarm.pending_bounties():
            # dispatch_event("bounty", bounty)
        pass

class EventParallel:
    def __init__(self, event, first):
        self.event = event
        self.func = None
        self.first = first

    def __call__(self, args, kwargs):
        gevent.spawn(trap_run, self.func, args, kwargs)

class EventSerialized:
    def __init__(self, event, first):
        self.event = event
        self.func = None
        self.first = first
        self.pending = gevent.queue.Queue()

    def task(self):
        for args, kwargs in self.pending:
            trap_run(self.func, args, kwargs)

    def __call__(self, args, kwargs):
        self.pending.put((args, kwargs))

registered_events = {}

def periodic(**kwargs):
    def periodic_decorator(func):
        delay = datetime.timedelta(**kwargs).total_seconds()
        setattr(func, "_arbiter_periodic", delay)
        return func
    return periodic_decorator

def periodicx(**kwargs):
    def periodic_decorator(func):
        delay = datetime.timedelta(**kwargs).total_seconds()
        setattr(func, "_arbiter_periodicx", delay)
        return func
    return periodic_decorator

def event(event_name, serialize=True, first=False):
    def event_decorator(func):
        if serialize:
            obj = EventSerialized(event_name, first)
        else:
            obj = EventParallel(event_name, first)
        setattr(func, "_arbiter_event", obj)
        return func
    return event_decorator

def event_register_instance(obj):
    # TODO: queue per function for serialization?
    for k in dir(obj):
        v = getattr(obj, k)
        e = getattr(v, "_arbiter_event", None)
        if e:
            e.func = v
            if hasattr(e, "task"):
                gevent.spawn(e.task)
            lst = registered_events.setdefault(e.event, [])
            if e.first:
                lst.insert(0, e)
            else:
                lst.append(e)
        periodic = getattr(v, "_arbiter_periodic", None)
        if periodic is not None:
            gevent.spawn(run_periodic, v, periodic)
        periodicx = getattr(v, "_arbiter_periodicx", None)
        if periodicx is not None:
            gevent.spawn(run_periodicx, v, periodicx)

def dispatch_event(__event_name, *args, **kwargs):
    lst = registered_events.get(__event_name, [])
    for f in lst:
        try:
            f(args, kwargs or {})
        except:
            log.exception("%s: Failed call %s:", __event_name, f)

def run_periodic(func, delay):
    while True:
        gevent.sleep(delay)
        try:
            func()
        except:
            log.exception("Periodic call %s failed:", func)

def run_periodicx(func, delay):
    while True:
        try:
            func()
        except:
            log.exception("Periodic call %s failed:", func)
        gevent.sleep(delay)

def trap_run(func, args, kwargs):
    try:
        func(*args, **kwargs)
    except SystemExit:
        raise
    except:
        log.exception("Error in %r:", func)
