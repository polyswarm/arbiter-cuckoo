# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import click.testing
import os.path
import random
import time

from arbiter.main import main

def test_main_none():
    # Hack attempting to keep the original ~/.arbiter.yaml file when
    # pytest-watch is running under both Python 2 and Python 3 environments.
    time.sleep(random.randint(0, 500) / 1000.0)

    configpath = os.path.expanduser("~/.arbiter.yaml")

    backup = None
    if os.path.exists(configpath):
        backup = open(configpath, "rb").read()
        os.unlink(configpath)

    r = click.testing.CliRunner().invoke(main)

    assert open(configpath, "rb").read() == b"""
host: 'localhost:31337'
addr: '0x0000000000000000000000000000000000000000'
password: 'password'
artifacts: ~/.samples
""".strip() + b"\n"

    backup and open(configpath, "wb").write(backup)

    assert r.exit_code == 1
    assert r.output == (
        "Configuration file '%s' not found, dropped default "
        "config to '%s'!\n" % (configpath, configpath)
    )

def test_main_config_404():
    r = click.testing.CliRunner().invoke(main, ["/tmp/404.cfg"])
    assert r.exit_code == 2
    assert r.output.startswith("Usage:")
