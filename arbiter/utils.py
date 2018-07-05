# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import hashlib
import hmac
import os
import tempfile
import time

class AtomicWrite:
    def __init__(self, fname):
        self.fname = fname
        self.tmpfile = None

    def write(self, data):
        self.tmpfile.write(data)

    def __enter__(self):
        self.tmpfile = tempfile.NamedTemporaryFile(delete=False)
        return self

    def __exit__(self, typ, value, tb):
        if not self.tmpfile:
            return
        if value is not None:
            os.remove(self.tmpfile.name)
        else:
            os.rename(self.tmpfile.name, self.fname)

def pct_agree(pct, v, n):
    if not n:
        return False
    return v >= (pct * n)

def verdict_fromuser(s):
    bitlist = []
    for v in s:
        if v in "tT1":
            bitlist.append(True)
        elif v in "fF0":
            bitlist.append(False)
        else:
            raise ValueError(v)
    return bitlist

def verdict_show(values):
    return "".join(str(v)[:1].upper() for v in values)

def verdict_compare(arbiter, expert, mask):
    disagree = False
    show = ""
    for v, m, x in zip(arbiter, mask, expert):
        if m:
            if v != x:
                disagree = True
                show += str(x)[:1]
            else:
                show += str(x)[:1].lower()
        else:
            show += "."
    if disagree:
        return show
    return False

def generate_token(secret, backend, timestamp=None):
    if not timestamp:
        timestamp = int(time.time())

    text = "%s.%s." % (backend, timestamp)
    h = hmac.new(secret, digestmod=hashlib.sha256)
    h.update(text.encode("utf8"))
    return "%s%s" % (text, h.hexdigest())

def validate_token(secret, token):
    parts = token.split(".")
    if len(parts) != 3:
        return False
    elif not parts[1].isdigit():
        return False

    # TODO: add minimum token validity time, if needed

    text = ".".join(parts[:2]) + "."
    h = hmac.new(secret, digestmod=hashlib.sha256)
    h.update(text.encode("utf8"))
    if hmac.compare_digest(h.hexdigest(), parts[2]):
        return parts[0]
    return False
