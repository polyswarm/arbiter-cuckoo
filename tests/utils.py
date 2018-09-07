# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

from arbiter.database import init_database, Base, DbSession
from arbiter.database import DbBounty

def db_init():
    uri = "postgresql://arbiter_test:arbiter_test@localhost/arbiter_test"
    init_database(uri, True)

def db_destroy():
    Base.metadata.drop_all(DbSession.kw['bind'])

def db_clear():
    s = DbSession()
    # Cascading delete
    s.query(DbBounty).delete()
    s.commit()
    s.close()
