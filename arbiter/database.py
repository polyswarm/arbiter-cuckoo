# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

import datetime
from sqlalchemy import create_engine, Column, ForeignKey
from sqlalchemy import Index, Integer, String, DateTime, Boolean
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
    expires = Column(DateTime, nullable=False)

    # Our ground truth as pre-serialized JSON
    truth_value = Column(JsonString, nullable=True)

    # Whether submission has been succesful
    truth_settled = Column(Boolean, nullable=False, default=False)

    # A bounty that requires manual intervention
    truth_manual = Column(Boolean, nullable=False, default=False)

    # Minimum time (block) at which we can settle the bounty
    # Also the time at which assertions must become available
    settle_block = Column(Integer, nullable=False)

    artifacts = relationship("DbArtifact",
                             backref=backref("bounty", lazy="joined"))

# Is-settled and current-block check
Index('ix_bounty_settle', DbBounty.truth_settled, DbBounty.settle_block)

class DbArtifact(Base):
    """An artifact with one or more analysis results"""
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True)
    bounty_id = Column(Integer,
                       ForeignKey("bounties.id"),
                       nullable=False)
    hash = Column(String(255))
    name = Column(String(255))
    verdict = Column(Integer, nullable=True)

    verdicts = relationship("DbArtifactVerdict",
                            backref=backref("artifact", lazy="joined"))

class DbArtifactVerdict(Base):
    """The verdict as given by an analysis source for an artifact"""
    __tablename__ = "artifact_verdicts"

    id = Column(Integer, primary_key=True)
    artifact_id = Column(Integer, ForeignKey("artifacts.id"), nullable=False,
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
