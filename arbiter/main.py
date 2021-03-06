# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

from __future__ import print_function

import gevent.monkey
gevent.monkey.patch_all()

import click
import logging
import os.path
import sys
import yaml

from web3.auto import w3 as web3

from arbiter.arbiterd import Arbiterd
from arbiter.balance import val_readable
from arbiter.config import ConfigFile
from arbiter.const import JOB_STATUS_NAMES, MINIMUM_STAKE_DEFAULT
from arbiter.database import init_database
from arbiter.utils import SimpleFormatter

default_conf_path = os.path.expanduser("~/.arbiter.yaml")

def initialize(path, clean=False):
    config = ConfigFile(path)
    init_database(config.dburi, clean)
    return config


@click.group()
@click.option("--debug", "-d", is_flag=True)
@click.option("--silent", is_flag=True)
@click.option("--config", "-c",
              required=False, default=default_conf_path,
              type=click.Path(exists=False))
@click.pass_context
def cli(ctx, debug, silent, config):
    level = logging.DEBUG if debug else logging.INFO
    fmt = "%(asctime)s %(name)s %(levelname)s: %(message)s"
    root = logging.getLogger()
    root.setLevel(level)
    if not silent:
        stream = logging.StreamHandler()
        stream.setFormatter(SimpleFormatter(fmt))
        root.addHandler(stream)

    logging.getLogger("urllib3").setLevel(logging.WARNING)

    if not ctx.invoked_subcommand:
        raise ValueError()

    ctx.meta["config_path"] = config
    if ctx.invoked_subcommand != "conf":
        if not os.path.exists(config):
            sys.exit("Configuration file %s not found" % config)
        if ctx.invoked_subcommand != "clean":
            ctx.meta["config"] = initialize(config)
            host = ctx.meta["config"].polyswarmd
            logfile = logging.FileHandler("arbiter.%s.log" % host)
            logfile.setFormatter(logging.Formatter(fmt))
            root.addHandler(logfile)

@cli.command()
@click.pass_context
def clean(ctx):
    """Reset database"""
    ctx.meta["config"] = initialize(ctx.meta["config_path"], True)
    print("Database reset")

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
@click.option("--manual", "-m", is_flag=True)
@click.pass_context
def run(ctx, manual):
    import resource
    try:
        _, limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (limit, limit))
    except ValueError:
        pass

    p = Arbiterd(ctx.meta["config"], manual)
    p.run()

@cli.command()
@click.option("--amount", "-a", default=MINIMUM_STAKE_DEFAULT)
@click.pass_context
def stake(ctx, amount):
    p = Arbiterd(ctx.meta["config"])

    print("Making staking deposit of %d wei (NCT).." % amount)

    if not p.stake(amount):
        print("ERROR: failed to make staking deposit")
        exit(-1)

    print("Staking was successful.")

@cli.command()
@click.argument("bounty")
@click.argument("vote")
def settle(bounty, vote):
    """Manually settle a bounty"""
    from arbiter.bounties import bounty_settle_manual
    votes = []
    for v in vote:
        if v in 'tT1':
            votes.append(True)
        elif v in 'fF0':
            votes.append(False)
        else:
            raise ValueError(v)
    bounty_settle_manual(bounty, votes)

@cli.command()
@click.pass_context
@click.argument("chain")
@click.argument("amount")
def relay(ctx, chain, amount):
    """Relay *to* chain"""
    from decimal import Decimal
    if chain not in ("side", "home"):
        raise ValueError(chain)

    amount = web3.toWei(Decimal(amount), "ether")
    if amount <= 0:
        raise ValueError(amount)

    p = Arbiterd(ctx.meta["config"]).polyswarm
    p.set_base_nonce()
    if chain == "side":
        logging.info("Transferring %s from home to side", amount)
        p.relay_deposit(amount, "home")
    else:
        logging.info("Transferring %s from side to home", amount)
        p.relay_withdraw(amount, "side")

@cli.command()
@click.pass_context
def balance(ctx):
    p = Arbiterd(ctx.meta["config"]).polyswarm
    p.set_base_nonce()
    for v in ("nct", "eth"):
        for c in ("side", "home"):
            balance = int(p.balance(v, chain=c))
            logging.info("%s %s %s", v, c, val_readable(balance, v))
    balance = int(p.staking_balance_withdrawable())
    logging.info("staking withdrawable %s", val_readable(balance, "nct"))
    balance = int(p.staking_balance_total())
    logging.info("staking total %s", val_readable(balance, "nct"))

@cli.command()
def bounties():
    from arbiter.database import DbSession, DbBounty

    print("Status".ljust(8), "GUID".ljust(36),
          "MRVS", "<Vote", ">Settle",
          "Value")

    S = {True: "*", False: " "}

    s = DbSession()
    for b in s.query(DbBounty).order_by(DbBounty.id).all():
        if not b.truth_value:
            value = "-"
        else:
            value = "".join(str(v)[:1] for v in  b.truth_value)
        print(b.status.ljust(8),
              b.guid,
              S[b.truth_manual] + S[b.revealed] + S[b.voted]  + S[b.settled],
               str(b.vote_before).ljust(5),
               str(b.settle_block).ljust(7),
              value.ljust(5),
              )

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
