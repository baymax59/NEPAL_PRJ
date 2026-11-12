"""Alembic migration environment.

The database URL comes from app settings (.env), not from alembic.ini,
so the password lives in exactly one place.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.db import models  # noqa: F401  (importing registers every table on Base.metadata)
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False keeps the app's own loggers working (e.g. during tests).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Write the migration SQL to the screen instead of running it (`alembic upgrade head --sql`).

    Useful when a database administrator must review the SQL before it is applied.
    """
    context.configure(
        dialect_name="postgresql",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
