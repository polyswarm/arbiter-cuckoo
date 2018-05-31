# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

from __future__ import print_function

import gevent.monkey
gevent.monkey.patch_all()

import click
import logging
import os.path
import sys
import yaml

from arbiter.config import ConfigFile
from arbiter.database import init_database
from arbiter.arbiterd import Arbiterd

default_conf_path = os.path.expanduser("~/.arbiter.yaml")

def initialize(path, clean=False, level=logging.INFO):
    logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                        level=level)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    config = ConfigFile(path)
    init_database(config.dburi, clean)
    return config

@click.group()
@click.option("--debug", "-d", is_flag=True)
@click.option("--clean", is_flag=True) # TODO: remove
@click.option("--config", "-c",
              required=False, default=default_conf_path,
              type=click.Path(exists=False))
@click.pass_context
def cli(ctx, debug, clean, config):
    if not ctx.invoked_subcommand:
        raise ValueError()

    if not os.path.exists(default_conf_path):
        if config == default_conf_path and ctx.invoked_subcommand == "run":
            # TODO: use explicit init function instead
            with open(default_conf_path, "w") as fp:
                yaml.dump(ConfigFile.defaults, fp)
            sys.exit(
                "Configuration file not found, dropped default "
                "config to '%s'!" % default_conf_path
            )
        else:
            raise ValueError("Configuration file not found")

    level = logging.DEBUG if debug else logging.INFO
    ctx.meta["config"] = initialize(config, clean, level)

@cli.command()
@click.pass_context
def run(ctx):
    p = Arbiterd(ctx.meta["config"])
    p.run()

@cli.command()
@click.argument("bounty")
@click.argument("verdict")
def settle(bounty, verdict):
    """Manually settle a bounty"""
    from arbiter.bounties import bounty_settle_manual
    verdicts = []
    for v in verdict:
        if v in 'tT1':
            verdicts.append(True)
        elif v in 'fF0':
            verdicts.append(False)
        else:
            raise ValueError(v)
    bounty_settle_manual(bounty, verdicts)

@cli.command()
def bounties():
    from arbiter.database import DbSession, DbBounty

    print("GUID".ljust(36), "Blck", "Fini ", "Value", "M")

    s = DbSession()
    for b in s.query(DbBounty).order_by(DbBounty.id).all():
        print(b.guid, b.settle_block, str(b.truth_settled).ljust(5),
              b.truth_value, "*" if b.truth_manual else "")

@cli.command()
def pending():
    from arbiter.database import DbSession, DbArtifactVerdict

    s = DbSession()
    #for av in s.query(DbArtifactVerdict).filter(DbArtifactVerdict.verdict.is_(None)).all():
    for av in s.query(DbArtifactVerdict).filter(DbArtifactVerdict.status != 0).all():
        print("ID:", av.id, "AVID:", av.artifact_id, "Backend:", av.backend, "S:", av.status, "EXP:", av.expires)
