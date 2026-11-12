"""Declarative base shared by all table models."""

from enum import StrEnum

from sqlalchemy import CheckConstraint, MetaData
from sqlalchemy.orm import DeclarativeBase

# Predictable constraint names, so Alembic can find and change them in later migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def in_check(column: str, allowed: type[StrEnum]) -> CheckConstraint:
    """CHECK constraint limiting a text column to the values of a StrEnum."""
    values = ", ".join(f"'{member.value}'" for member in allowed)
    return CheckConstraint(f"{column} IN ({values})", name=f"{column}_allowed")
