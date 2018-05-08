# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import requests

from arbiter.sources import VerdictSource

class Cuckoo(VerdictSource):
    def configure(self, config):
        url = config["url"]
        if not url.endswith("/"):
            url += "/"
        self.cuckoo_url = url
        self.options = config.get("options")

    def submit_artifact(self, artifact):
        body = {}
        if self.options:
            body["options"] = self.options
        body["custom"] = artifact.id
        files = {"file": (artifact.filename, artifact.fetch())}
        req = requests.post(self.cuckoo_url + "api/task",
                            data=body,
                            files=files)
        req.raise_for_status()
        resp = req.json()
        if not resp["success"]:
            raise ValueError(resp)

        # resp["task_id"] ...
