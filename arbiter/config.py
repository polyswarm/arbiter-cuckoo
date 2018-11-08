# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import base64
import datetime
import logging
import os.path
import yaml

from arbiter.const import MINIMUM_STAKE_DEFAULT

log = logging.getLogger(__name__)

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
        "polyswarmd": "polyswarmd.polyswarm.io",
        "apikey": "a"*32,
        "addr": "",
        "addr_privkey": "",
        "minimum_stake": MINIMUM_STAKE_DEFAULT,
        "dashboard_password": "",
        "api_secret": "",
        "artifacts": "~/.artifacts",
        "dburi": "postgresql://arbiter:arbiter@localhost/arbiter",
        "expires": datetime.timedelta(days=5),
        "analysis_backends": {},
        "trusted_experts": [],
        "testing_mode": False,
        "monitor_bind": "10.1.0.12:12333",
    }

    def __init__(self, path=None):
        if not path:
            self.properties = {}
            self.properties.update(self.defaults)
        else:
            self.properties = yaml.safe_load(open(path, "rb")) or {}
            for k, v in self.defaults.items():
                if k not in self.properties:
                    self.properties[k] = v
        for k in ("dashboard_password", "api_secret"):
            if not self.properties.get(k):
                log.warning("Please configure `%s`!. Creating random secret...", k)
                pw = base64.b64encode(os.urandom(16)).decode("utf8").rstrip("=")
                self.properties[k] = pw

    def __getattr__(self, name):
        if name in self.properties:
            return self.properties[name]
        if name in self.defaults:
            return self.defaults[name]
        raise AttributeError(name)

    @property
    def api_secret(self):
        return self.__getattr__("api_secret").encode("utf8")

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
