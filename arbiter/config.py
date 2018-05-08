# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import os.path
import yaml

class ConfigFile(object):
    def __init__(self, path):
        self.properties = yaml.safe_load(open(path, "rb"))

    @property
    def host(self):
        return self.properties.get("host", "localhost")

    @property
    def addr(self):
        return self.properties.get("addr", 0)

    @property
    def password(self):
        return self.properties.get("password")

    @property
    def artifacts(self):
        return os.path.expanduser(
            self.properties.get("artifacts", "~/.samples")
        )

    @property
    def dburi(self):
        return self.properties.get(
            "dburi", "postgresql://arbiter:arbiter@localhost/arbiter"
        )

    @property
    def verdict_sources(self):
        return self.properties.get("verdict_sources", {})
