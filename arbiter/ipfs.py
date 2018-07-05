# Copyright (C) 2018 Bremer Computer Security B.V.
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
cache_path = None

class IPFSNotFoundError(Exception):
    pass

def ipfs_download(hash, uri=None):
    if not r_valid_hash.match(hash):
        raise ValueError("Invalid IPFS hash %r" % hash)
    if uri is None:
        uri = hash
    path = os.path.join(cache_path, hash)
    if not os.path.exists(path):
        # TODO: atomic write
        if hash != uri:
            log.debug("Fetching IPFS hash %s (%s)", hash, uri)
        else:
            log.debug("Fetching IPFS hash %s", hash)
        req = requests.get("http://%s/artifacts/%s" % (ipfs_host, uri))
        log.debug("Download status: %s", req.status_code)
        if req.status_code == 404:
            raise IPFSNotFoundError
        req.raise_for_status()
        with AtomicWrite(path) as fp:
            # TODO: small writes
            fp.write(req.content)
    return path

def ipfs_open(hash, uri=None):
    return open(ipfs_download(hash, uri), "rb")

def ipfs_json(hash, uri=None):
    return json.load(open(ipfs_download(hash, uri), "rb"))
