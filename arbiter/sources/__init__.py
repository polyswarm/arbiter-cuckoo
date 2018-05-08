# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

# Write-once list of all verdict sources, used by API and backend
verdict_sources = {}

def load_sources(config):
    global verdict_sources
    for name, conf in config.items():
        plugin = conf.get('plugin', name)

        mod = __import__('arbiter.sources.' + plugin)
        mod = getattr(mod.sources, plugin)

        # TODO:
        plugin_class = None
        for obj in dir(mod):
            if obj == 'VerdictSource':
                continue
            elif obj[0].isalpha() and obj[0].isupper():
                plugin_class = getattr(mod, obj, None)
                break
        if not plugin_class:
            raise ValueError('Missing plugin class for %s' % plugin)

        inst = plugin_class(name)
        inst.configure(conf)
        verdict_sources[name] = inst

    return verdict_sources

class VerdictSource(object):
    """Defines the API for communication with verdict sources"""
    def __init__(self, name):
        self.name = name
        # TODO
        self.api_key = name

    def configure(self, conf):
        """Set up verdict source with plugin-specific configuration"""

    def check_api_key(self, x_api_key):
        # TODO: constant-time compare or HMAC
        return self.api_key == x_api_key

    def submit_artifact(self, artifact):
        """Submit an artifact for analysis"""
        raise NotImplementedError
