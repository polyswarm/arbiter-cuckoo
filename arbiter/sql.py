# Copyright 2007-2018, the SQLAlchemy authors and contributors.
# SQLAlchemy and its documentation are licensed under the MIT license.
# Source: http://docs.sqlalchemy.org/en/latest/core/custom_types.html

import json
import uuid

from sqlalchemy.types import TypeDecorator, CHAR, String
from sqlalchemy.dialects.postgresql import UUID as PsqlUUID

class JsonString(TypeDecorator):
    impl = String

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(String())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return json.loads(value)

class UUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type, otherwise uses
    CHAR(32), storing as stringified hex values.

    """
    impl = CHAR

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PsqlUUID())
        else:
            return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        elif isinstance(value, uuid.UUID):
            return "%.32x" % value.int
        # Assume string
        return value.replace("-", "")

    def process_result_value(self, value, dialect):
        return value
