# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import os
import tempfile

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
