# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import requests

from arbiter.backends import AnalysisBackend

class Cuckoo(AnalysisBackend):
    def configure(self, config):
        url = config["url"]
        if not url.endswith("/"):
            url += "/"
        self.cuckoo_url = url
        self.api_version = config.get("api_version", "cuckoo_api")
        self.options = config.get("options")

    def submit_artifact(self, artifact):
        body = {}
        if self.options:
            body["options"] = self.options
        body["custom"] = artifact.url
        files = {"file": (artifact.name, artifact.fetch())}
        if self.api_version == "distributed":
            path = "api/task"
        else:
            path = "tasks/create/file"
        req = requests.post(self.cuckoo_url + path,
                            data=body, files=files)
        req.raise_for_status()
        resp = req.json()
        if self.api_version == "distributed":
            if resp.get("success") != "OK":
                raise ValueError(resp)
            return {"task_ids": resp.get("task_ids")}
        if "task_id" not in resp:
            raise ValueError(resp)
        return {"task_id": resp["task_id"]}
