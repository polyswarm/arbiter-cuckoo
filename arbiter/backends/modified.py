# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import requests

from arbiter.backends import AnalysisBackend

class Modified(AnalysisBackend):
    def configure(self, config):
        url = config['url']
        if not url.endswith('/'):
            url += '/'
        self.cuckoo_url = url
        self.options = config.get("options")

    def submit_artifact(self, artifact):
        body = {}
        if self.options:
            body["options"] = self.options
        body["custom"] = artifact.url
        files = {"file": (artifact.name, artifact.fetch())}
        req = requests.post(self.cuckoo_url + "v1/tasks/create/file",
                            headers={"X-Arbiter": self.name},
                            data=body, files=files)
        req.raise_for_status()
        resp = req.json()
        if "task_ids" not in resp:
            raise ValueError(resp)
        return {"task_ids": resp["task_ids"]}

    def health_check(self):
        req = requests.get(self.cuckoo_url + "v1/cuckoo/status")
        req.raise_for_status()
        data = req.json()
        report = {
            "machinestotal": data["machines"]["total"],
            "machinesused": data["machines"]["total"] - data["machines"]["available"],
        }
        return report
