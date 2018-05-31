# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

from arbiter.ipfs import ipfs_open

class Artifact:
    def __init__(self, id, name, hash, url):
        self.id = id
        self.name = name
        self.hash = hash
        self.url = url

    def fetch(self):
        return ipfs_open(self.hash)
