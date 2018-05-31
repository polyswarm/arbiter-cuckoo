#!/usr/bin/env python

import gevent.monkey
gevent.monkey.patch_all()

from base58 import b58encode
from gevent.pywsgi import WSGIServer
from gevent.queue import Queue
from geventwebsocket.handler import WebSocketHandler
from json import dumps
from os import urandom
from random import choice, randrange
from requests import post
from time import time
from hashlib import sha256
from uuid import uuid4

import logging
from flask import Flask, request, jsonify, Response

BLOCK_MINE_SPEED = 15
CUCKOO_SPEED = 180
BOUNTIES_PER_BLOCK = 4
MAX_PENDING = 100

AUTO_GENERATE = 0

log = logging.getLogger(__name__)
app = Flask(__name__)

_start = time()

class state:
    bounties = {}
    ipfs = {}
    assertions = {}
    block = 1
    connected = False
    logged = False

events = Queue()
jobs = Queue()

def ipfs_buf(buf):
    prefix = b"\x12\x20"
    digest = sha256(buf).digest()
    return b58encode(prefix + digest)

def random_file():
    ext = ".py" # TODO?
    n = randrange(2, 7)
    return b58encode(urandom(n)).rstrip("=") + ext

def gen_bounty(files=None):
    if files:
        n = len(files)
    else:
        n = randrange(1, 5)
        files = [(random_file(), "print(%r)\n" % random_file())
                 for _ in range(n)]

    meta = []
    for f in files:
        meta.append({"name": f[0], "hash": ipfs_buf(f[1])})

    g = str(uuid4())

    ipfs = ipfs_buf(dumps(meta, sort_keys=True))
    state.ipfs[ipfs] = {"meta": meta, "files": [f[1] for f in files]}
    log.debug("create %s", g)
    k = {
        "amount": "123",
        "author": "0x123",
        "expiration": "%s" % (state.block + 2,),
        "guid": g,
        "resolved": False,
        "uri": ipfs,
        "verdicts": [False] * n
    }
    state.bounties[g] = k
    # TODO: API?
    if choice([True, False]):
        state.assertions[g] = [{
            "bounty_guid": g,
            "author": "0xe23bc28b143259aa0ce9c9c949f882c6acb9822b",
            "bid": "60282812500000000000",
            "mask": [True] * n,
            "verdicts": [choice([True, False]) for i in range(n)],
            "metadata": "Nobody cared who I was until I put on the mask",
        }]
    else:
        state.assertions[g] = []
    return k

def ok(val):
    return jsonify({"status": "OK", "result": val})

def err(code, val):
    return jsonify({"status": "ERROR", "result": val}), code

def w(k, v):
    m = dumps({"event": k, "data": v})
    log.debug("send %r", m)
    return m

def block_update():
    if not state.connected:
        return

    state.block += 1
    events.put(w("block", {"number": state.block}))

    if not AUTO_GENERATE:
        return

    for _ in range(BOUNTIES_PER_BLOCK):
        if len(state.bounties) >= MAX_PENDING:
            break
        m = gen_bounty()
        events.put(w("bounty", m))

def receive(ws):
    while True:
        message = ws.receive()
        if message is None:
            break
        log.debug("ws < %r", message)

def stream_events(ws):
    log.info("WebSocket connection")
    state.connected = True
    try:
        gevent.spawn(receive, ws)
        gevent.sleep(0.1) # Deal with ws4py bug
        ws.send(w("block", {"number": state.block}))
        for b in state.bounties.values():
            ws.send(w("bounty", b))
        events.put(w("block", {"number": state.block}))
        while True:
            m = events.get()
            if m is None:
                log.info("Fuck")
                continue
            try:
                ws.send(m)
            except Exception as e:
                log.warning("ws.send: %r", e)
                break
    finally:
        state.connected = False
    return []

@app.route("/accounts/<acct>/balance/<kind>")
def account_balance(acct, kind):
    return ok("1000000000000")

@app.route("/bounties", methods=["POST"])
def submit_bounty():
    files = []
    for f in request.files.getlist("file"):
        data = f.stream.read()
        files.append((f.filename, data))
    if files:
         g = gen_bounty(files)
         events.put(w("bounty", g))
         return ok(g)
    return err(400, "No files")

@app.route("/bounties/<ignore>")
def bounties_pending(ignore):
    return ok([])

@app.route("/bounties/<guid>/assertions")
def bounties_assertions(guid):
    log.info("assertions %s", guid)
    b = state.assertions.pop(guid, None)
    if b is None:
        return err(404, "No such bounty for assertions")
    return ok(b)

@app.route("/bounties/<guid>/settle", methods=["POST"])
def bounties_settle(guid):
    log.info("settle %s", guid)
    wait_next_block()
    b = state.bounties.pop(guid, None)
    if b is None:
        return err(404, "No such bounty")
    state.ipfs.pop(b["uri"], None)
    return ok("We did it")

@app.route("/artifacts/<ipfs>")
def artifacts_meta(ipfs):
    m = state.ipfs.get(ipfs)
    if not m:
        return err(404, "No such file")
    return ok(m["meta"])

@app.route("/artifacts/<ipfs>/<int:idx>")
def artifacts_data(ipfs, idx):
    m = state.ipfs.get(ipfs)
    if not m or idx >= len(m["files"]):
        return err(404, "No such file")
    return Response(m["files"][idx], mimetype='application/octet-stream')

# Cuckoo API
@app.route("/api/task", methods=["POST"])
def api_task():
    aid = request.form["custom"]
    def cuckoo_submit():
        gevent.sleep(CUCKOO_SPEED)
        jobs.put(aid)
    gevent.spawn(cuckoo_submit)
    return jsonify({"success": "OK", "task_id": 1, "task_ids": [1]})

def run_server(bind=":8091"):
    host, port = bind.split(":")
    log.info("Starting server for %r on %r", app, bind)
    ws = {"/events": stream_events}
    def xapp(environ, start_response):
        path = environ["PATH_INFO"]
        handler = ws.get(path)
        if handler and "wsgi.websocket" in environ:
            return handler(environ["wsgi.websocket"])
        return app(environ, start_response)
    server = WSGIServer((host, int(port)), xapp, handler_class=WebSocketHandler)
    logging.getLogger("geventwebsocket.handler").setLevel(logging.WARNING)
    server.serve_forever()

next_block_event = gevent.event.Event()

def block_miner():
    while True:
        gevent.sleep(BLOCK_MINE_SPEED)
        block_update()
        next_block_event.set()
        next_block_event.clear()

def wait_next_block():
    cur = state.block
    while True:
        next_block_event.wait()
        if cur != state.block:
            break
        gevent.sleep(0.05)

def job_processor():
    while True:
        m = jobs.get()
        log.info("Submit %s", m)
        v = choice([0, 50, 100]) # None
        try:
            post(m, headers={"Authorization": "Bearer cuckoo"},
                 json={"verdict_value": v})
        except:
            log.exception("Failed to submit %s", m)

if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                        level=logging.INFO)
    gevent.spawn(job_processor)
    gevent.spawn(block_miner)
    run_server()
