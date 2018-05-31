# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

from gevent import subprocess

from arbiter.backends import AnalysisBackend
from arbiter.const import VERDICT_SAFE, VERDICT_MALICIOUS

class Process(AnalysisBackend):
    def configure(self, config):
        self.path = config["path"]

    def submit_artifact(self, artifact):
        cmd = ["env",
               "ARTIFACT_ID=%s" % artifact.id,
               "ARTIFACT_NAME=%s" % artifact.name,
               self.path]
        artifact_data = artifact.fetch()
        p = subprocess.Popen(cmd, stdin=artifact_data)
        p.wait()
        # Compatible with e.g. clamscan
        if p.returncode == 0:
            return VERDICT_SAFE
        return VERDICT_MALICIOUS
