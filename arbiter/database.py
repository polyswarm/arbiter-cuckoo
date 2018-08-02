# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import datetime

from sqlalchemy import Index, Integer, String, DateTime, Boolean
from sqlalchemy import create_engine, Column, ForeignKey
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, backref, relationship

from arbiter.sql import JsonString, UUID

Base = declarative_base()
DbSession = sessionmaker()

# TODO: some indexes need to be created where appropriate.

class DbBounty(Base):
    """A bounty with one or more artifacts"""
    __tablename__ = "bounties"

    id = Column(Integer, primary_key=True)
    guid = Column(UUID, unique=True)
    created = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    amount = Column(String, nullable=False)
    author = Column(String, nullable=False)
    num_artifacts = Column(Integer, nullable=False)

    status = Column(ENUM("active", "finished", "aborted", name="bounties_status"),
                    nullable=False, default="active", index=True)

    # Our ground truth as pre-serialized JSON, must only be set when ready to
    # settle.
    # TODO: maybe just a bit string or string with T/F
    truth_value = Column(JsonString, nullable=True)

    # A bounty that requires manual intervention
    truth_manual = Column(Boolean, nullable=False, default=False)

    # Expiration block for assertions
    expiration_block = Column(Integer, nullable=False)

    # The time (block) **before** which we must vote on the bounty
    vote_block = Column(Integer, nullable=False)
    voted = Column(Boolean, nullable=False, default=False)

    # The time (block) at which assertions should become available
    reveal_block = Column(Integer, nullable=False)
    revealed = Column(Boolean, nullable=False, default=False)
    # Cache assertions for UI
    assertions = Column(JsonString, nullable=True)

    # The time (block) at which we can settle the bounty
    settle_block = Column(Integer, nullable=False)
    settled = Column(Boolean, nullable=False, default=False)

    artifacts = relationship("DbArtifact",
                             backref=backref("bounty", lazy="noload"))

Index("ix_bounty_voted", DbBounty.voted, DbBounty.vote_block)
Index("ix_bounty_revealed", DbBounty.revealed, DbBounty.reveal_block)
Index("ix_bounty_settled", DbBounty.settled, DbBounty.settle_block)

class DbArtifact(Base):
    """An artifact with one or more analysis results"""
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True)
    bounty_id = Column(Integer,
                       ForeignKey("bounties.id", ondelete="cascade"),
                       nullable=False)
    hash = Column(String(255))
    name = Column(String(255))


    # Set if processing is complete,
    processed = Column(Boolean, nullable=False, default=False, index=True)

    # TODO: create an index or view on date_trunc for the dashboard graph
    processed_at = Column(DateTime, nullable=True)
    processed_at_interval = Column(Integer, nullable=True, index=True)

    verdict = Column(Integer, nullable=True)

    verdicts = relationship("DbArtifactVerdict",
                            backref=backref("artifact", lazy="noload"))

class DbArtifactVerdict(Base):
    """The verdict as given by an analysis source for an artifact"""
    __tablename__ = "artifact_verdicts"

    id = Column(Integer, primary_key=True)
    artifact_id = Column(Integer,
                         ForeignKey("artifacts.id", ondelete="cascade"),
                         nullable=False,
                         index=True)
    backend = Column(String(32), nullable=False)
    # Unique: (artifact_id, backend)

    # Their verdict
    verdict = Column(Integer, nullable=True)

    # Asynchronous state bookkeeping
    status = Column(Integer, nullable=False, index=True)
    expires = Column(DateTime)
    meta = Column(JsonString, nullable=True)

def init_database(dburi, cleanup=False):
    engine = create_engine(dburi)
    DbSession.configure(bind=engine)
    if cleanup:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
