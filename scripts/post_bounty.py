# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import requests
import json
import sys
import os

if len(sys.argv) < 2:
    print "usage:", sys.argv[0], "<file0> [file1] [file..]"
    exit(-1)

files = []

for fn in sys.argv[1:]:
    files.append(( "file", (os.path.basename(fn), open(fn,"rb").read())))

r = requests.post("http://0:31337/accounts/d6625a8a1a8a3bdb953d20a9310333d362b137da/unlock",
                  headers={"Content-Type": "application/json"},
                  json={"password": "user_password"})
r.raise_for_status()

r = requests.post("http://0:31337/artifacts", files=files)
r.raise_for_status()

artifact_res = r.json()

if "result" not in artifact_res.keys():
    print "something went wrong with uploading artifacts"
    exit(-1)

manifest_hash = artifact_res['result']

r = requests.post("http://0:31337/bounties", json={
    "amount":  "62500000000000000",
    "uri": manifest_hash, "duration": 4
})
r.raise_for_status()

bounty_res = r.json()
bounty = bounty_res['result']

print "> posted bounty:"
print "  guid         : %s" % (bounty['guid'])
print "  manifest uri : %s" % (bounty['uri'])
print "  author       : %s" % (bounty['author'])
print "  expiry block : %s" % (bounty['expiration'])
print "  NCT amount   : %s" % (bounty['amount'])
