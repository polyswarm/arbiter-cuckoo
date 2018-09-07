# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

# Write-once list of all analysis backends
analysis_backends = {}

def load_backends(config):
    global analysis_backends
    for name, conf in config.items():
        plugin = conf.get("plugin", name)

        mod = __import__("arbiter.backends." + plugin)
        mod = getattr(mod.backends, plugin)

        # TODO:
        plugin_class = None
        for obj in dir(mod):
            if obj == "AnalysisBackend":
                continue
            elif obj[0].isalpha() and obj[0].isupper():
                val = getattr(mod, obj, None)
                try:
                    if issubclass(val, AnalysisBackend):
                        plugin_class = val
                        break
                except TypeError:
                    # Not a class
                    pass
        if not plugin_class:
            raise ValueError("Missing plugin class for %s" % plugin)

        inst = plugin_class(name, conf.get("trusted", False),
                            conf.get("weight", 1))
        inst.configure(conf)
        analysis_backends[name] = inst

    return analysis_backends

class AnalysisBackend(object):
    """Defines the API for communication with analysis backends"""

    def __init__(self, name, trusted, weight):
        self.name = name
        self.trusted = trusted
        self.weight = weight
        # TODO
        self.api_key = name

    def configure(self, conf):
        """Set up analysis backend with plugin-specific configuration"""

    def cancel_artifact(self, av_id, artifact):
        """Job no longer applies (e.g. due to timeout)"""

    def submit_artifact(self, av_id, artifact, previous_task=None):
        """Submit an artifact for analysis. If a task is resubmitted (e.g. at
        application start), the previous task may contain metadata of the
        previous, interrupted task.

        Possible return values:
        * None
        * Dictionary with JSON-serializable items (can be empty); if it
          contains 'verdict', the job is completed.
        * An integer that indicates the verdict (for synchronous tasks)
        """
        raise NotImplementedError

    def health_check(self):
        pass
