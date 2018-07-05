# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import requests

from arbiter.backends import AnalysisBackend

class Process(AnalysisBackend):
    def configure(self, config):
        self.url = config["url"]

    def submit_artifact(self, artifact):
        files = {"file": (artifact.name, artifact.fetch())}
        req = requests.post(self.url, files=files,
                            headers={"X-Arbiter": self.name})
        req.raise_for_status()
        verdict = req.json()["verdict"]
        if verdict is None or isinstance(verdict, int):
            return verdict
        raise ValueError(verdict)
