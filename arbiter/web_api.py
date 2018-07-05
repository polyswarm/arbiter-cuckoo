# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

# API used by frontend and analysis backends.

import datetime
import functools
import os.path
import time

from flask import (
    Flask, Response, jsonify, request, abort, redirect, send_from_directory
)

from sqlalchemy import and_, or_, func
from sqlalchemy.sql import exists

from arbiter.backends import analysis_backends
from arbiter.component import WSGIComponent
from arbiter.const import JOB_STATUS_DONE, JOB_STATUS_NAMES
from arbiter.dashboard import dashboard_ws
from arbiter.database import DbSession, DbBounty, DbArtifact, DbArtifactVerdict
from arbiter.events import dispatch_event
from arbiter.utils import validate_token

app = Flask(__name__)
dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard")

class APIComponent(WSGIComponent):
    name = "api"
    bind = ":9080"
    ws = {"/kraken/tentacle": dashboard_ws}
    app = app

    def __init__(self, parent):
        self.artifact_interval = parent.artifact_interval
        self.polyswarm = parent.polyswarm
        self.api_secret = parent.config.api_secret
        self.dashboard_password = parent.config.dashboard_password

def dashboard_auth(f):
    def check_auth(auth):
        # TODO: constant-time compare
        return auth.password == app.component.dashboard_password

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth):
            return Response("Authentication required.", 401,
                            {"WWW-Authenticate": 'Basic realm="Arbiter"'})
        return f(*args, **kwargs)
    return decorated

def check_apikey(view):
    @functools.wraps(view)
    def hook(*args, **kwargs):
        api_key = request.headers.get("Authorization")
        if not api_key or not api_key.lower().startswith("bearer "):
            abort(401, "The Authorization header is required")

        token = api_key[7:]
        backend = validate_token(app.component.api_secret, token)
        if not backend or not backend in analysis_backends:
            abort(401, "Invalid API key specified")

        ab = analysis_backends[backend]
        return view(*args, analysis_backend=ab, **kwargs)
    return hook

@app.after_request
def apply_caching(response):
    # For dashboard; TODO - set to something sane
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

# Dashboard
# {{{

def missing_time_steps(t, cur, step_time):
    if t is None:
        return []

    # We only need to add the first and last
    steps = []
    expect_next = t + step_time
    if expect_next < cur:
        steps.append(expect_next)

    expect_last = cur - step_time
    if expect_next != expect_last and expect_last > t:
        steps.append(expect_last)

    return steps

@app.route("/dashboard/charts/artifacts")
@dashboard_auth
def artifact_datapoints():
    unow = datetime.datetime.utcnow()
    ustart = unow - datetime.timedelta(days=5)
    start = int(time.mktime(ustart.timetuple()))
    now = int(time.mktime(unow.timetuple()))
    data = []

    s = DbSession()
    try:
        step_time = app.component.artifact_interval
        rs = s.query(DbArtifact.processed_at_interval, func.count(1)) \
            .filter(DbArtifact.processed_at_interval.isnot(None)) \
            .filter(DbArtifact.processed_at_interval > start) \
            .group_by(DbArtifact.processed_at_interval) \
            .order_by(DbArtifact.processed_at_interval)

        prev = None
        for r in rs:
            stamp = r.processed_at_interval
            for step in missing_time_steps(prev, stamp, step_time):
                data.append([step, 0])
            data.append([stamp, r[1]])
            prev = stamp

        if prev:
            if (now - prev) > step_time:
                # We've stopped seeing entries, so end with 0
                data.append([prev + step_time, 0])
                data.append([now, 0])
            #elif data[-1][0] > now:
            #    # Extrapolate the last entry to prevent a "dip"
            #    last = data[-1][0]
            #    boost = (step_time - (last - now)) / float(step_time)
            #    data[-1][1] = data[-1][1] / boost

    finally:
        s.close()

    if len(data) == 1:
        data.insert(0, [data[0][0] - step_time, 0])
    data.sort(key=lambda v: tuple(v))

    return jsonify({
        "start": data[0][0] if data else start,
        "end": data[-1][0] if data else now,
        "data": data,
    })

@app.route("/dashboard/bounties/<guid>", methods=["POST"])
@dashboard_auth
def dashboard_manual_verdict(guid):
    """Set manual verdict for a bounty"""
    verdicts = request.json["verdicts"]
    if not isinstance(verdicts, list):
        abort(400, "Verdicts is not a list")
    for verdict in verdicts:
        if not isinstance(verdict, int) or verdict < 0 or verdict > 100:
            abort(400, "Invalid verdict value")

    s = DbSession()
    try:
        b = s.query(DbBounty).with_for_update().filter_by(guid=guid).one()
        if not b.truth_manual:
            abort(403, "Bounty not in manual mode")
        if len(verdicts) != b.num_artifacts:
            abort(400, "This bounty requires %s verdicts" % b.num_artifacts)
        if b.truth_settled:
            abort(403, "Bounty already settled")
        b.truth_value = verdicts
        s.add(b)
        s.commit()
    finally:
        s.close()

    #dispatch_event("bounty_artifact_verdict", bounty_id)
    return jsonify({"status": "OK"})

@app.route("/")
@dashboard_auth
def index():
    return redirect("/dashboard/")

@app.route("/dashboard/")
@dashboard_auth
def dashboard_index():
    return send_from_directory(dashboard_path, "index.html")

@app.route("/dashboard/<path:static_path>")
@dashboard_auth
def dashboard_files(static_path):
    return send_from_directory(dashboard_path, static_path)

def _gather_bounty_data(b, verbose=True):
    data = {
        "guid": b.guid,
        "author": b.author,
        "amount": b.amount,
        "created": str(b.created),
        "num_artifacts": b.num_artifacts,
        "truth_value": b.truth_value,
        "truth_settled": b.truth_settled,
        "truth_manual": b.truth_manual,
        "settle_block": b.settle_block,
    }
    pending_artifacts = 0
    if verbose:
        data["assertions"] = b.assertions
    artifacts = []
    for a in b.artifacts:
        verdicts = {}
        if verbose:
            for av in a.verdicts:
                status = JOB_STATUS_NAMES.get(av.status, av.status)
                verdicts[av.backend] = {"verdict": av.verdict,
                                        "status": status,
                                        "meta": av.meta}
        artifacts.append({
            "name": a.name,
            "verdict": a.verdict,
            "processed": a.processed,
        })
        if verbose:
            artifacts[-1]["verdicts"] = verdicts
            artifacts[-1]["hash"] = a.hash
        if not a.processed:
            pending_artifacts += 1
        data["artifacts"] = artifacts
    else:
        for a in b.artifacts:
            if not a.processed:
                pending_artifacts += 1
    data["pending_artifacts"] = pending_artifacts
    return data

@app.route("/dashboard/bounties/<guid>")
@dashboard_auth
def dashboard_bounties_guid(guid):
    s = DbSession()
    b = s.query(DbBounty).filter_by(guid=guid) \
        .order_by(DbBounty.id).one_or_none()
    if b is None:
        return jsonify({"error": "No such bounty"}), 404
    data = _gather_bounty_data(b)
    s.close()
    return jsonify(data)

@app.route("/dashboard/bounties/pending")
@dashboard_auth
def dashboard_bounties_pending():
    # Bounties that are being processed or need to be submitted
    s = DbSession()
    bs = s.query(DbBounty).filter_by(truth_settled=False) \
        .filter(or_(DbBounty.truth_manual.is_(False),
                    DbBounty.truth_value.isnot(None))) \
        .order_by(DbBounty.id)
    bounties = [_gather_bounty_data(b, False) for b in bs]
    s.close()
    return jsonify(bounties)

@app.route("/dashboard/bounties/manual")
@dashboard_auth
def dashboard_bounties_manual():
    """All bounties that need a manual verdict"""
    s = DbSession()
    bs = s.query(DbBounty).filter_by(truth_manual=True) \
        .filter_by(truth_settled=False) \
        .order_by(DbBounty.id)
    bounties = [_gather_bounty_data(b, False) for b in bs]
    s.close()
    return jsonify(bounties)

# }}}

# Analysis backend API
# {{{

@app.route("/artifacts")
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

    app.logger.debug("Received verdict for artifact #%s from %s", artifact_id,
                     analysis_backend.name)
    dispatch_event("verdict_update", artifact_id)

    return jsonify({"status": "OK"})
