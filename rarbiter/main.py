# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import click
import logging
import os.path
import sys

from rarbiter.config import ConfigFile
from rarbiter.interact import PolySwarmd

CONFIG = b"""
host: 'localhost:31337'
addr: '0x0000000000000000000000000000000000000000'
password: 'password'
artifacts: ~/.samples
"""

@click.command()
@click.argument("configfile", required=False, type=click.Path(exists=True))
@click.option("--debug", "-d", is_flag=True)
def main(configfile, debug):
    defaultpath = os.path.expanduser("~/.rarbiter.yaml")
    if not configfile and not os.path.exists(defaultpath):
        open(defaultpath, "wb").write(CONFIG.strip() + b"\n")
        sys.exit(
            "Configuration file '%s' not found, dropped default "
            "config to '%s'!" % (configfile or defaultpath, defaultpath)
        )

    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    config = ConfigFile(configfile or defaultpath)
    p = PolySwarmd(config)
    p.init()
    p.run()
