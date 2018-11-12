# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import requests

from arbiter.backends import AnalysisBackend

class Cuckoo(AnalysisBackend):
    def configure(self, config):
        # API
        self.cuckoo_url = config["url"]
        if not self.cuckoo_url.endswith("/"):
            self.cuckoo_url += "/"

        # Web interface
        if "view" in config:
            self.cuckoo_view_url = config["view"]
            if not self.cuckoo_view_url.endswith("/"):
                self.cuckoo_view_url += "/"
            self.href_pattern = "%sanalysis/%s/summary"
        else:
            self.cuckoo_view_url = self.cuckoo_url
            self.href_pattern = "%stasks/%s/view"

        self.api_version = config.get("api_version", "cuckoo_api")
        self.api_token = config.get("api_token", "")
        self.options = config.get("options")

    def submit_artifact(self, av_id, artifact, previous_task=None):
        body = {}
        if self.options:
            body["options"] = self.options
        body["custom"] = artifact.url
        files = {"file": (artifact.name, artifact.fetch())}
        if self.api_version == "distributed":
            path = "api/task"
        else:
            path = "tasks/create/file"
        headers = {"X-Arbiter": self.name}
        if self.api_token:
            headers["Authorization"] = "Bearer %s" % self.api_token
        req = requests.post(self.cuckoo_url + path,
                            headers=headers,
                            data=body, files=files)
        req.raise_for_status()
        resp = req.json()
        task_id = None
        if self.api_version == "distributed":
            if resp.get("success") != "OK":
                raise ValueError(resp)
            task_ids = resp["task_ids"]
            if len(task_ids) != 1:
                # Not yet supported
                raise ValueError(resp)
            task_id = task_ids[1]
        else:
            if "task_id" not in resp:
                raise ValueError(resp)
            task_id = resp["task_id"]

        return {"task_id": task_id,
                "href": self.href_pattern % (self.cuckoo_view_url, task_id)}

    def health_check(self):
        headers = {}
        if self.api_token:
            headers["Authorization"] = "Bearer %s" % self.api_token
        req = requests.get(self.cuckoo_url + "v1/cuckoo/status", headers=headers)
        req.raise_for_status()
        data = req.json()
        report = {
            "cpu": data["cpuload"][0],
            "memtotal": data["memtotal"] / 1024,
            "memused": (data["memtotal"] - data["memavail"]) / 1024,
            "machinestotal": data["machines"]["total"],
            "machinesused": data["machines"]["total"] - data["machines"]["available"],
        }
        if data["diskspace"]:
            # FIXME
            total = used = 0
            for v in data["diskspace"].values():
                total += v["total"]
                used += v["used"]
                break
        return report
