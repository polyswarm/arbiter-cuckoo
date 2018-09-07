# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import hashlib

from arbiter.ipfs import ipfs_open

class Artifact(object):
    def __init__(self, id, name, hash, url):
        self.id = id
        self.name = name
        self.hash = hash
        self.url = url
        self._sha256 = None

    def fetch(self):
        return ipfs_open(self.hash)

    def sha256(self):
        if not self._sha256:
            s = hashlib.sha256()
            with self.fetch() as fp:
                while True:
                    tmp = fp.read(4096)
                    if not tmp:
                        break
                    s.update(tmp)
            self._sha256 = s.hexdigest()
        return self._sha256
