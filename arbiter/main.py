# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import click
import logging
import os.path
import sys

from arbiter.config import ConfigFile
from arbiter.database import init_database
from arbiter.interact import PolySwarmd

CONFIG = b"""
host: 'localhost:31337'
addr: '0x0000000000000000000000000000000000000000'
password: 'password'
artifacts: ~/.samples
dburi: 'postgresql://arbiter:arbiter@localhost/arbiter'
"""

@click.command()
@click.argument("configfile", required=False, type=click.Path(exists=True))
@click.option("--debug", "-d", is_flag=True)
def main(configfile, debug):
    defaultpath = os.path.expanduser("~/.arbiter.yaml")
    if not configfile and not os.path.exists(defaultpath):
        open(defaultpath, "wb").write(CONFIG.strip() + b"\n")
        sys.exit(
            "Configuration file '%s' not found, dropped default "
            "config to '%s'!" % (configfile or defaultpath, defaultpath)
        )

    logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                        level=logging.DEBUG if debug else logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    config = ConfigFile(configfile or defaultpath)
    init_database(config.dburi)

    p = PolySwarmd(config)
    p.init()
    p.run()
