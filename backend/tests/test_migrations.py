"""Database migrations create, remove and re-create the schema cleanly."""

from sqlalchemy import inspect, text

from alembic import command
from app.db.models import EMBEDDING_DIM
from app.db.session import engine

EXPECTED_TABLES = {"cases", "case_documents", "document_chunks", "case_events", "ingestion_runs"}


def table_names() -> set[str]:
    return set(inspect(engine).get_table_names())


def test_upgrade_creates_all_tables(migrated_db):
    assert EXPECTED_TABLES <= table_names()


def test_downgrade_to_empty_then_upgrade_again(migrated_db, alembic_cfg):
    command.downgrade(alembic_cfg, "base")
    assert not EXPECTED_TABLES & table_names()

    command.upgrade(alembic_cfg, "head")
    assert EXPECTED_TABLES <= table_names()


def test_models_and_migrations_are_in_sync(migrated_db, alembic_cfg):
    """Fails if app/db/models.py was changed without creating a migration for it."""
    command.check(alembic_cfg)


def test_embedding_column_matches_model_dimension(migrated_db):
    with engine.connect() as conn:
        column_type = conn.execute(
            text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = 'document_chunks'::regclass AND attname = 'embedding'"
            )
        ).scalar_one()

    assert column_type == f"vector({EMBEDDING_DIM})"
