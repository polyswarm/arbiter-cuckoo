# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import requests
import json
import sys
import os
from web3.auto import w3 as web3

if len(sys.argv) < 4:
    print("usage:", sys.argv[0], "<account_address> <privkey> <file0> [file1] [file..]")
    exit(-1)

account_addr = sys.argv[1]
privkey = sys.argv[2]

files = []

for fn in sys.argv[3:]:
    files.append(( "file", (os.path.basename(fn), open(fn,"rb").read())))

r = requests.post("http://0:31337/artifacts", files=files)
r.raise_for_status()

artifact_res = r.json()

if "result" not in artifact_res.keys():
    print("something went wrong with uploading artifacts")
    exit(-1)

manifest_hash = artifact_res['result']

r = requests.post("http://0:31337/bounties?account=%s" % (account_addr), json={
    "amount":  "62500000000000000",
    "uri": manifest_hash, "duration": 1
})
r.raise_for_status()

result = r.json()

if result['status'] != "OK":
    print("Something bad happened")
    exit(-1)

transactions = []
for transaction in result['result']['transactions']:
    signed = web3.eth.account.signTransaction(transaction, privkey)
    transactions.append(bytes(signed["rawTransaction"]).hex())

r = requests.post("http://0:31337/transactions", json={
    'transactions' : transactions
})

bounty_res = r.json()
bounty = bounty_res['result']['bounties'][0]

print("> posted bounty:")
print("  guid         : %s" % (bounty['guid']))
print("  manifest uri : %s" % (bounty['uri']))
print("  author       : %s" % (bounty['author']))
print("  expiry block : %s" % (bounty['expiration']))
print("  NCT amount   : %s" % (bounty['amount']))
