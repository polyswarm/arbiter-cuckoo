# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import json
import logging
import os.path
import re
import requests

from arbiter.utils import AtomicWrite

log = logging.getLogger(__name__)

r_valid_hash = re.compile(r"^[a-zA-Z0-9]+$")

ipfs_host = None
ipfs_apikey = None
cache_path = None

class IPFSNotFoundError(Exception):
    pass

def _ipfs_download(hash, uri):
    if uri is None:
        uri = hash
    if hash != uri:
        log.debug("Fetching IPFS hash %s (%s)", hash, uri)
    else:
        log.debug("Fetching IPFS hash %s", hash)

    headers = {
        "Authorization": "Bearer %s" % ipfs_apikey,
    }
    r = requests.get(
        "https://%s/artifacts/%s" % (ipfs_host, uri), headers=headers
    )
    #log.debug("Download status: %s", r.status_code)
    if r.status_code == 404:
        raise IPFSNotFoundError(uri)
    r.raise_for_status()
    return r.content

def ipfs_download(hash, uri=None):
    if not r_valid_hash.match(hash):
        raise ValueError("Invalid IPFS hash %r" % hash)
    path = os.path.join(cache_path, hash)
    if not os.path.exists(path):
        content = _ipfs_download(hash, uri)
        with AtomicWrite(path) as fp:
            fp.write(content)
    return path

def ipfs_open(hash, uri=None):
    return open(ipfs_download(hash, uri), "rb")

def ipfs_json(hash, uri=None, cache=True):
    if not cache:
        return json.loads(_ipfs_download(hash, uri))
    return json.load(open(ipfs_download(hash, uri), "rb"))
