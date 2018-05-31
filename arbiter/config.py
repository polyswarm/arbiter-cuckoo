# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import datetime
import os.path
import yaml

def repr_timedelta(dumper, data):
    # Fun for days
    r = {}
    for k in ("days", "seconds", "microseconds", "milliseconds",
              "minutes", "hours", "weeks"):
        v = getattr(data, k, 0)
        if v != 0:
            r[k] = v
    return dumper.represent_data(r)

yaml.add_representer(datetime.timedelta, repr_timedelta)

class ConfigFile(object):
    defaults = {
        "bind": ":9080",
        "url": "http://localhost:9080",
        "host": "localhost:31337",
        "addr": 0,
        "artifacts": "~/.artifacts",
        "dburi": "postgresql://arbiter:arbiter@localhost/arbiter",
        "expires": datetime.timedelta(days=5),
        "analysis_backends": {},
    }

    def __init__(self, path):
        self.properties = yaml.safe_load(open(path, "rb")) or {}

    def __getattr__(self, name):
        if name in self.properties:
            return self.properties[name]
        if name in self.defaults:
            return self.defaults[name]
        raise AttributeError(name)

    @property
    def artifacts(self):
        return os.path.expanduser(self.__getattr__("artifacts"))

    @property
    def expires(self):
        exp = self.__getattr__("expires")
        if isinstance(exp, dict):
            return datetime.timedelta(**exp)
        if isinstance(exp, int):
            return datetime.timedelta(hours=int(exp))
        return exp
