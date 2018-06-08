# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

# API used by frontend and analysis backends.

import functools
import math
import os.path
import random
import time

from flask import Flask, jsonify, request, abort, redirect, send_from_directory

from sqlalchemy import and_
from sqlalchemy.sql import exists

from arbiter.backends import analysis_backends
from arbiter.component import WSGIComponent
from arbiter.const import JOB_STATUS_DONE
from arbiter.dashboard import dashboard_ws
from arbiter.database import DbSession, DbArtifact, DbArtifactVerdict
from arbiter.events import dispatch_event

app = Flask(__name__)
dashboard_path = os.path.join(os.getcwd(), "dashboard/dist")

class APIComponent(WSGIComponent):
    name = "api"
    bind = ":9080"
    ws = {"/kraken/tentacle": dashboard_ws}
    app = app

    def __init__(self, parent):
        self.polyswarm = parent.polyswarm

def check_apikey(view):
    @functools.wraps(view)
    def hook(*args, **kwargs):
        # TODO: embed analysis backend name in API key for lookup purposes
        # TODO: use bearer token
        api_key = request.headers.get("Authorization")
        if not api_key or not api_key.lower().startswith("bearer "):
            abort(401, "The Authorization header is required")

        token = api_key[7:]
        for backend in analysis_backends.values():
            if backend.check_api_key(token):
                break
        else:
            abort(401, "Invalid API key specified")

        return view(*args, analysis_backend=backend, **kwargs)

    return hook

@app.after_request
def apply_caching(response):
    # For dashboard; TODO - set to something sane
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

@app.route("/dashboard/charts/artifacts")
def artifact_datapoints():
    N = 100
    now = time.time()
    start = time.time() - (5*3600*24)
    step = (now - start) / float(N - 1)
    data = []
    while len(data) < N:
        i = len(data)
        v = int(40 + 20 * math.sin(0.4 * i + 0.05 * random.random()))
        data.append([int(start + i * step), v])

    return jsonify({
        "start": int(start),
        "end": int(now),
        "data": data,
    })

@app.route("/", methods=['GET'])
def index():
    return redirect("/dashboard/")

@app.route("/dashboard/", methods=['GET'])
def dashboard_index():
    return send_from_directory(dashboard_path, "index.html")

@app.route("/dashboard/<path:static_path>", methods=['GET'])
def dashboard_files(static_path):
    return send_from_directory(dashboard_path, static_path)

@app.route("/artifacts", methods=["GET"])
@check_apikey
def list_artifacts(analysis_backend):
    s = DbSession()
    artifacts = []

    q = s.query(DbArtifact).filter(
        ~exists().where(and_(
            DbArtifactVerdict.artifact_id == DbArtifact.id,
            DbArtifactVerdict.backend == analysis_backend.name
        ))
    )

    for artifact in q:
        artifacts.append(artifact.id)

    s.close()

    return jsonify(artifacts)

@app.route("/artifact/<int:artifact_id>", methods=["POST"])
@check_apikey
def action_artifact(analysis_backend, artifact_id):
    if not isinstance(request.json, dict):
        abort(400, "No JSON POST body found")

    if "error" in request.json:
        pass

    if "verdict_value" not in request.json:
        abort(400, "Missing verdict_value")

    verdict_value = request.json["verdict_value"]
    if verdict_value is not None:
        verdict_value = int(verdict_value)
        if verdict_value < 0 or verdict_value > 100:
            abort(400, "Invalid verdict value")

    s = DbSession()
    verdict = s.query(DbArtifactVerdict) \
        .with_for_update().filter(and_(
            DbArtifactVerdict.backend == analysis_backend.name,
            DbArtifactVerdict.artifact_id == artifact_id
        )).first()

    if not verdict:
        s.close()
        abort(404, "Artifact #%d not found" % artifact_id)

    if verdict.status == JOB_STATUS_DONE:
        s.close()
        abort(403, "Verdict for artifact #%s already submitted" % artifact_id)

    verdict.status = JOB_STATUS_DONE
    verdict.verdict = verdict_value
    s.add(verdict)
    s.commit()
    s.close()

    app.logger.info("Received verdict for artifact #%s from %s", artifact_id,
                    analysis_backend.name)
    dispatch_event("verdict_update", (artifact_id,))

    return jsonify({"status": "OK"})

# Debug helpers {{{
@app.route("/tasks/create/file", methods=["POST"])
def cuckoo_hack_test():
    return jsonify({"success": "OK", "task_id": 123})

@app.route("/hack/<int:block>")
def block_hack_test(block):
    dispatch_event("block", (block,))
    return "Dispatched event\n"

@app.route("/cli/check_settle")
def cli_check_settle():
    dispatch_event("check_settle")
    return "OK\n"
# }}}

if __name__ == "__main__":
    # For dashboard
    app.run()
