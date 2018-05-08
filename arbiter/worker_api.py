# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import functools

from flask import Flask, jsonify, request, abort
from sqlalchemy import and_
from sqlalchemy.sql import exists

from arbiter.database import DbSession, DbVerdict, DbArtifact
from arbiter.sources import verdict_sources

app = Flask(__name__)

def check_apikey(view):
    @functools.wraps(view)
    def hook(*args, **kwargs):
        # TODO: embed verdict source name in API key for lookup purposes
        if not request.headers.get('X-Api-Key'):
            abort(401)

        x_api_key = request.headers.get('X-Api-Key')
        for verdict_source in verdict_sources.values():
            if verdict_source.check_api_key(x_api_key):
                break
        else:
            abort(401, "Invalid API key specified")

        return view(*args, verdict_source=verdict_source, **kwargs)

    return hook

@app.route("/artifacts", methods=['GET'])
@check_apikey
def list_artifacts(verdict_source):
    s = DbSession()
    artifacts = []

    q = s.query(DbArtifact).filter(
        ~exists().where(and_(
            DbVerdict.artifact_id == DbArtifact.id,
            DbVerdict.verdict_source == verdict_source.name
        ))
    )

    for artifact in q:
        artifacts.append(artifact.id)

    s.close()

    return jsonify(artifacts)

@app.route("/artifact/<int:artifact_id>", methods=["POST"])
@check_apikey
def action_artifact(verdict_source, artifact_id):
    if not isinstance(request.json, dict):
        abort(500, "No JSON POST body found")

    if "verdict_value" not in request.json.keys():
        abort(500, "Missing verdict_value")

    verdict_value = request.json["verdict_value"]

    s = DbSession()

    q = s.query(DbArtifact).filter_by(id = artifact_id)

    if q.count() != 1:
        s.close()
        abort(404, "Artifact #%d not found" % (artifact_id))

    q = s.query(DbVerdict).filter(and_(
            DbVerdict.verdict_source == verdict_source.name,
            DbVerdict.artifact_id == artifact_id
        ))

    if q.count() > 0:
        s.close()
        abort(500, "Verdict for this artifact already submitted")

    db_verdict = DbVerdict(
        verdict_source=verdict_source.name,
        verdict_value=verdict_value,
        artifact_id=artifact_id
    )

    s.add(db_verdict)
    s.commit()
    s.close()

    return jsonify({"status": "OK"})
