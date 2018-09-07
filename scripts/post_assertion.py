# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

import requests
import json
import sys
import os
from web3.auto import w3 as web3

if len(sys.argv) < 5:
    print("usage:", sys.argv[0], "<account_address> <privkey> <guid> <assertions>")
    exit(-1)

account_addr = sys.argv[1]
privkey = sys.argv[2]
guid = sys.argv[3]

files = []

assertions = sys.argv[4]
assertions_bool = []

for a in assertions:
    if a == "t":
        assertions_bool.append(True)
    else:
        assertions_bool.append(False)

r = requests.post("http://0:31337/bounties/%s/assertions?account=%s" % (guid, account_addr), json={
    "bid" : "62500000000000000",
    "mask" : [ True ] * len(assertions),
    "verdicts" : assertions_bool
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

print(r.json())
