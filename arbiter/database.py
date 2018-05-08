# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
DbSession = sessionmaker()

class DbVerdict(Base):
    __tablename__ = "verdicts"

    id = Column(Integer, primary_key=True)
    verdict_source = Column(String(32))
    verdict_value = Column(Integer, nullable=True)
    artifact_id = Column(Integer)

class DbArtifact(Base):
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True)
    bounty_id = Column(Integer)
    artifact_hash = Column(String(255))
    artifact_path = Column(String(255))
    artifact_filename = Column(String(255))

class DbBounty(Base):
    __tablename__ = "bounties"

    id = Column(Integer, primary_key=True)
    guid = Column(String(255))
    expiration = Column(Integer)
    settled = Column(Integer)

def init_database(dburi):
    engine = create_engine(dburi)
    DbSession.configure(bind=engine)
    #Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
