#!/usr/bin/env python
# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import gevent.monkey
gevent.monkey.patch_all()

import argparse
import base58
import hashlib
import json
import logging
import os
import random
import requests
import time
import uuid

from gevent.pywsgi import WSGIServer
from gevent.queue import Queue
from geventwebsocket.handler import WebSocketHandler

from flask import Flask, request, jsonify, Response

try:
    from polydb import known_malicious
except ImportError:
    known_malicious = set()

parser = argparse.ArgumentParser(description="Polymock")
parser.add_argument("-m", "--mine-speed", type=int, default=15, help="Mine block every X seconds")
parser.add_argument("-c", "--cuckoo-speed", type=int, default=32, help="Return verdict after X +/- 30 seconds")
parser.add_argument("-b", "--bounties", type=int, default=4, help="Bounties per block")
parser.add_argument("-p", "--pending", type=int, default=200, help="Maximum total pending bounties")
parser.add_argument("-a", "--artifacts", type=int, default=3, help="Maximum artifacts per bounty")
parser.add_argument("-A", "--assertions", type=int, default=10, help="Maximum assertions per bounty")
parser.add_argument("-g", "--generate", type=int, default=50, help="Number of bounties to generate over time")
parser.add_argument("-B", "--bind", default=":8091")

EXPIRATION_WINDOW = 5
ARBITER_VOTE_WINDOW = 25
ASSERTION_REVEAL_WINDOW = 25

ARGS = parser.parse_args()
AUTO_GENERATE = ARGS.generate
START_TIME = int(time.time())

API_TOKENS = {
    "cuckoo": "cuckoo.1529584950.8acb2fb28f10f6095457e5783e47f88965efbd5278fefd7006d533ddb5d60e9d",
    "zer0m0n": "zer0m0n.1529584950.6b85d54d7ab9ef0db1623dedae5031d0f43ec52fe5cfc7e81f6fae48bd4ec89b",
}

ASSERTION_AUTHORS = [
    # Trusted
    "0xe23bc28b143259aa0ce9c9c949f882c6acb9822b",
]

while len(ASSERTION_AUTHORS) < 16:
    ASSERTION_AUTHORS.append("0x" + str(uuid.uuid4()).replace("-", ""))

ASSERTION_META = [
    "",
    "Nobody cared who I was until I put on the mask",
    "This artifact deleted my system32",
]

log = logging.getLogger(__name__)
app = Flask(__name__)

_start = time.time()

class state:
    bounties = {}
    ipfs = {}
    assertions = {}
    block = 1
    connected = False
    logged = False
    task_id = 1

events = Queue()
jobs = Queue()

def ipfs_buf(buf):
    prefix = b"\x12\x20"
    digest = hashlib.sha256(buf.encode("utf8")).digest()
    return base58.b58encode(prefix + digest).decode("utf8")

def random_file():
    ext = ".py" # TODO?
    n = random.randrange(2, 7)
    return base58.b58encode(os.urandom(n)).decode("utf8").rstrip("=") + ext

def ws_bounty(b):
     # Polyswarm only sends a subset
     event = {}
     for k in ("guid", "author", "amount", "uri", "expiration"):
         event[k] = b[k]
     return event

def gen_bounty(files=None):
    if files:
        n = len(files)
    else:
        n = random.randrange(1, ARGS.artifacts + 1)
        files = [(random_file(), "print(%r)\n" % random_file())
                 for _ in range(n)]

    meta = []
    for f in files:
        meta.append({"name": f[0], "hash": ipfs_buf(f[1])})

    g = str(uuid.uuid4())

    ipfs = ipfs_buf(json.dumps(meta, sort_keys=True))
    state.ipfs[ipfs] = {"meta": meta, "files": [f[1] for f in files]}
    log.debug("create %s", g)
    k = {
        "guid": g,
        "author": "0x%08x" % random.randrange(1, 1000000000000),
        "amount": "%s" % random.randrange(1, 1000000000000),
        "uri": ipfs,
        "num_artifacts": n,
        "expiration": state.block + EXPIRATION_WINDOW,
        "assigned_arbiter": "0x1f50cf288b5d19a55ac4c6514e5ba6a704bd03ec",
        "resolved": False,

        "bloom": [],
        "voters": [],
        "verdicts": [False] * n,
        "bloom_votes": [],
    }
    state.bounties[g] = k

    # TODO: assertion on timer, assertion events

    asserts = state.assertions[g] = []
    a = random.randrange(0, ARGS.assertions + 1)
    authors = list(ASSERTION_AUTHORS)
    random.shuffle(authors)
    for author in authors[:a]:
        asserts.append({
            "author": author,
            "bid": "60282812500000000000",
            "mask": [random.choice([True, False, False]) for i in range(n)],
            "commitment": str(random.randrange(1, 0xffffffff)),
            "nonce": str(random.randrange(1, 0xfffffffff)),
            "verdicts": [random.choice([True, False]) for i in range(n)],
            "metadata": random.choice(ASSERTION_META),
        })
    return k

def ok(val):
    return jsonify({"status": "OK", "result": val})

def err(code, val):
    return jsonify({"status": "ERROR", "result": val}), code

def w(k, v):
    m = json.dumps({"event": k, "data": v})
    log.debug("send %r", m)
    return m

def block_update():
    global AUTO_GENERATE
    if not state.connected:
        return

    state.block += 1
    events.put(w("block", {"number": state.block}))

    if not AUTO_GENERATE:
        return

    for _ in range(ARGS.bounties):
        if len(state.bounties) >= ARGS.pending:
            break
        if AUTO_GENERATE and AUTO_GENERATE is not True:
            AUTO_GENERATE -= 1
        m = gen_bounty()
        events.put(w("bounty", ws_bounty(m)))

def receive(ws):
    while True:
        message = ws.receive()
        if message is None:
            break
        log.debug("ws < %r", message)

def stream_events(ws):
    log.info("WebSocket connection")
    ws.send(w("connected", {"start_time": START_TIME}))
    state.connected = True
    try:
        gevent.spawn(receive, ws)
        gevent.sleep(0.1) # Deal with ws4py bug
        ws.send(w("block", {"number": state.block}))
        for b in state.bounties.values():
            ws.send(w("bounty", ws_bounty(b)))
        events.put(w("block", {"number": state.block}))
        while True:
            m = events.get()
            if m is None:
                continue
            try:
                ws.send(m)
            except Exception as e:
                log.warning("ws.send: %r", e)
                break
    finally:
        state.connected = False
    return []

@app.route("/balances/<acct>/<kind>")
def account_balance(acct, kind):
    return ok("10000000000000000000000000")

@app.route("/bounties", methods=["POST"])
def submit_bounty():
    files = []
    for f in request.files.getlist("file"):
        data = f.stream.read()
        files.append((f.filename, data))
    if files:
         g = gen_bounty(files)
         events.put(w("bounty", ws_bounty(g)))
         return ok(g)
    return err(400, "No files")

@app.route("/bounties/<guid>")
def bounties_data(guid):
    if guid in ("pending", "active"):
        # TODO
        return ok([])

    b = state.bounties.get(guid)
    if not b:
        return err(404, "No such bounty")
    return ok(b)

@app.route("/bounties/<guid>/assertions")
def bounties_assertions(guid):
    bounty = state.bounties.get(guid)
    if not bounty:
        return err(404, "No such bounty")
    elif state.block < (bounty["expiration"] + ARBITER_VOTE_WINDOW + ASSERTION_REVEAL_WINDOW):
        log.info("assertions at %s, window %s", state.block, bounty["expiration"] + ARBITER_VOTE_WINDOW + ASSERTION_REVEAL_WINDOW)
        return err(403, "Assertions not yet revealed")

    b = state.assertions.pop(guid, None)
    log.info("assertions %s %s", guid,
             len(b) if b is not None else b)
    if b is None:
        return err(404, "No such bounty for assertions")
    return ok(b)

@app.route("/bounties/<guid>/vote", methods=["POST"])
def bounties_vote(guid):
    if random.random() < 0.2:
        return err(500, "Random failure")
    log.info("vote %s", guid)
    b = state.bounties.get(guid)
    if b is None:
        return err(404, "No such bounty")
    elif not ((b["expiration"] + ARBITER_VOTE_WINDOW) > state.block):
        log.info("vote at %s, window %s", state.block, b["expiration"] + ARBITER_VOTE_WINDOW)
        return err(403, "Vote window closed")
    wait_next_block()
    return ok({"transactions": [
        {"nonce": 1, "chainId": 1, "gasPrice": 1, "gas": "0x1000000000000"}
    ]})

@app.route("/bounties/<guid>/settle", methods=["POST"])
def bounties_settle(guid):
    if random.random() < 0.2:
        return err(500, "Random failure")
    log.info("settle %s", guid)
    wait_next_block()
    b = state.bounties.pop(guid, None)
    if b is None:
        return err(404, "No such bounty")
    state.ipfs.pop(b["uri"], None)
    return ok({"transactions": [
        {"nonce": 1, "chainId": 1, "gasPrice": 1, "gas": "0x1000000000000"}
    ]})

@app.route("/transactions", methods=["POST"])
def transactions():
    return ok("thanks")

@app.route("/balances/<acct>/staking/deposit", methods=["POST"])
def staking_deposit():
    return ok("thanks")

@app.route("/balances/<acct>/staking/total")
def staking_total(acct):
    return ok("10000000000000000000000000")

@app.route("/balances/<acct>/staking/withdrawable")
def staking_withdrawable():
    return ok(1)

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
@app.route("/tasks/create/file", methods=["POST"])
@app.route("/v1/tasks/create/file", methods=["POST"])
def api_task():
    aid = request.form["custom"]
    backend = request.headers.get("X-Arbiter")
    hash = hashlib.sha256(request.files["file"].read()).hexdigest()
    xtime = max(1, int(ARGS.cuckoo_speed * 0.2))
    t = random.randrange(max(0, ARGS.cuckoo_speed - xtime),
                         ARGS.cuckoo_speed + xtime)
    log.info("Received a request to analyze %s (backend: %s | speed: %s | sha256: %s)", aid, backend, t, hash)
    def cuckoo_submit():
        gevent.sleep(t)
        jobs.put((aid, backend, hash))
    if random.random() < 0.001:
        # Randomly fail
        return jsonify({"error": "Something went wrong"}), 500
    gevent.spawn(cuckoo_submit)
    task_id = state.task_id
    state.task_id += 1
    return jsonify({"success": "OK",
                    "task_id": task_id,
                    "task_ids": [task_id]})

@app.route("/machines/list")
def cuckoo_machines_list():
    return jsonify({
        "machines": [
            {"name": "cuckoo1", "platform": "windows", "tags": ["polyswarm", "adobe9"]},
            {"name": "cuckoo2", "platform": "windows", "tags": ["polyswarm", "adobe9"]},
        ]
    })

@app.route("/cuckoo/status")
@app.route("/v1/cuckoo/status")
def cuckoo_status():
    return jsonify({
        "cpu_count": 40,
        "cpuload": [
            0.11,
            0.04,
            0.01
        ],
        "diskspace": {
            "analyses": {
                "free": 47373534306304,
                "total": 59997882417152,
                "used": 12624348110848
            },
            "binaries": {
                "free": 47373534306304,
                "total": 59997882417152,
                "used": 12624348110848
            }
        },
        "hostname": "polymock.cuckoo.sh",
        "machines": {
            "available": 5,
            "total": 20
        },
        "memavail": 210535316,
        "memory": 20.281096304638012,
        "memtotal": 264097104,
        "processes": {},
        "tasks": {
            "completed": 4,
            "pending": 13780,
            "reported": 3725,
            "running": 0,
            "total": 17610
        },
        "version": "2.0.6"
    })

def run_server(bind):
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
        gevent.sleep(ARGS.mine_speed)
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
        url, backend, hash = jobs.get()
        if known_malicious:
            if hash in known_malicious:
                v = 100
            else:
                v = 0
        else:
            #v = random.choice([0, 50, 100] * 3 + [None])
            v = random.choice([0, 100])
        log.info("Submit %s for %s (score = %s)", url, backend, v)
        try:
            token = API_TOKENS.get(backend)
            r = requests.post(
                url, headers={"Authorization": "Bearer %s" % token},
                json={"verdict_value": v}
            )
            r.raise_for_status()
        except:
            log.exception("Failed to submit %s", url)

if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                        level=logging.INFO)
    gevent.spawn(job_processor)
    gevent.spawn(block_miner)
    run_server(ARGS.bind)
