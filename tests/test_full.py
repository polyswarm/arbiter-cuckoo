# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import json
import os.path
import requests

from arbiter.config import ConfigFile
from arbiter.interact import PolySwarmd

def test_full_run():
    # If no production-ready configuration is available, then we crash hard.
    filepath = os.path.expanduser("~/.arbiter.yaml")
    if not os.path.exists(filepath):
        raise Exception(
            "must have configuration in place for functional tests"
        )

    p = PolySwarmd(ConfigFile(filepath))
    p.init(start_threads=False)

    r = requests.post(
        "http://%s/artifacts" % p.config.host,
        files=(
            ("file", ("filename1", b"content1" + os.urandom(8))),
            ("file", ("filename2", b"content2" + os.urandom(8))),
            ("file", ("filename3", b"content3" + os.urandom(8))),
        )
    )
    r.raise_for_status()

    ipfs = r.json()["result"]

    r = requests.post(
        "http://%s/bounties" % p.config.host,
        json={
            "amount": "62500000000000000",
            "uri": ipfs,
            "duration": 5,
        },
    )
    r.raise_for_status()

    guid = r.json()["result"]["guid"]

    p.ws.on_message(None, json.dumps({
        "event": "assertion",
        "data": {
            "bounty_guid": guid,
            "author": "0x1f50Cf288b5d19a55ac4c6514e5bA6a704BD03EC",
            "index": 0,
            "bid": "62500000000000000",
            "mask": [True, False, True],
            "verdicts": [True, False, False],
            "metadata": "assert!",
        },
    }))

    p.ws.on_message(None, json.dumps({
        "event": "bounty",
        "data": {
            "guid": "c988199d-cd12-415d-93e8-09cf56689d19",
            "expiration": "1649",
            "uri": ipfs,
            "amount": "62500000000000000",
            "author": "0x1f50Cf288b5d19a55ac4c6514e5bA6a704BD03EC",
        },
    }))
