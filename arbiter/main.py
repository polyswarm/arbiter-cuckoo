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

from arbiter.arbiterd import Arbiterd
from arbiter.config import ConfigFile
from arbiter.const import JOB_STATUS_NAMES
from arbiter.database import init_database

default_conf_path = os.path.expanduser("~/.arbiter.yaml")

def initialize(path, clean=False):
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

    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                        level=level)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    ctx.meta["config_path"] = config
    if ctx.invoked_subcommand != "conf":
        if not os.path.exists(config):
            sys.exit("Configuration file %s not found" % conf)
        ctx.meta["config"] = initialize(config, clean)

@cli.command()
@click.pass_context
def conf(ctx):
    config = ctx.meta["config_path"]
    if os.path.exists(config):
        sys.exit("Configuration file %s already exists" % config)
    cfg = ConfigFile(None)
    with open(config, "w") as fp:
        yaml.dump(cfg.properties, fp)
    print("Configuration file", config, "created")

@cli.command()
@click.pass_context
def run(ctx):
    import resource
    try:
        _, limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (limit, limit))
    except ValueError:
        pass

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
        if not b.truth_value:
            value = "-"
        else:
            value = "".join(str(v)[:1] for v in  b.truth_value)
        print(b.guid, str(b.settle_block).ljust(4),
              str(b.truth_settled).ljust(5), value.ljust(5),
              "*" if b.truth_manual else "")

@cli.command()
def pending():
    from arbiter.database import DbSession, DbArtifactVerdict

    s = DbSession()
    #for av in s.query(DbArtifactVerdict).filter(DbArtifactVerdict.verdict.is_(None)).all():
    for av in s.query(DbArtifactVerdict).filter(DbArtifactVerdict.status != 0).all():
        status = JOB_STATUS_NAMES.get(av.status, av.status)
        print("ID: %5s" % av.id,
              "AVID: %5s" % av.artifact_id,
              "Backend: %-10s" % av.backend,
              "S: %-10s" % status,
              "EXP:", av.expires)
