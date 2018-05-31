# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import json
import logging

from geventwebsocket import WebSocketError

from arbiter.backends import analysis_backends

log = logging.getLogger(__name__)

ui_broadcast_ws = set()
ui_data_list = {}

def send(ws, kind, data):
    msg = {"msg": kind}
    msg[kind] = data
    ws.send(json.dumps(msg, separators=(',',':')))

def dashboard_ws(ctx, ws):
    for k, v in ui_data_list.items():
        send(ws, k, v)

    ui_broadcast_ws.add(ws)
    try:
        while True:
            message = ws.receive()
            if message is None:
                break
            log.debug("ws < %r", message)
    finally:
        ui_broadcast_ws.discard(ws)
    return []
