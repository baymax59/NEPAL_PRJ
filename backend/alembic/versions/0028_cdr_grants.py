"""Grant cm_runtime access to the cdr schema; extend cm_grant_runtime() to cover it.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-12

Migration 0027 created the cdr schema but cm_grant_runtime() (defined in 0014) only
covered the public schema, so the caseapp runtime user had no access. This migration:
  1. Grants the cdr schema to cm_runtime immediately.
  2. Replaces cm_grant_runtime() so future db_roles runs also refresh cdr grants.
"""

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

# Tables whose append-only triggers block UPDATE/DELETE; only SELECT+INSERT is needed.
# (Granting more is harmless since triggers enforce the constraint, but keeping it
# tight matches the security intent.)
_APPEND_ONLY = ("records", "custody_events", "validation_errors")


def upgrade() -> None:
    # 1. Immediate grants so the running application can access the cdr schema.
    op.execute("GRANT USAGE ON SCHEMA cdr TO cm_runtime")
    op.execute("GRANT SELECT, INSERT, UPDATE ON cdr.import_batches TO cm_runtime")
    for tbl in _APPEND_ONLY:
        op.execute(f"GRANT SELECT, INSERT ON cdr.{tbl} TO cm_runtime")

    # 2. Replace cm_grant_runtime() to also cover the cdr schema on future runs.
    op.execute("""
        CREATE OR REPLACE FUNCTION cm_grant_runtime() RETURNS void LANGUAGE plpgsql AS $$
        DECLARE
            t record;
            deletable text[] := ARRAY[
                'document_pages', 'document_chunks', 'document_provisions',
                'case_events', 'case_entities', 'uploads', 'upload_chunks',
                'case_access_grants', 'audit_events', 'user_mfa'
            ];
        BEGIN
            -- public schema (original logic)
            GRANT USAGE ON SCHEMA public TO cm_runtime;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cm_runtime;
            FOR t IN SELECT c.oid, c.relname
                     FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                     WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') LOOP
                EXECUTE format('REVOKE ALL ON TABLE %I FROM cm_runtime', t.relname);
                IF t.relname = 'alembic_version' THEN
                    EXECUTE format('GRANT SELECT ON TABLE %I TO cm_runtime', t.relname);
                ELSIF EXISTS (
                    SELECT 1 FROM pg_trigger g
                    WHERE g.tgrelid = t.oid
                      AND g.tgname = 'cm_' || t.relname || '_permanent'
                      AND t.relname <> 'audit_events'
                ) THEN
                    EXECUTE format('GRANT SELECT, INSERT ON TABLE %I TO cm_runtime', t.relname);
                ELSIF t.relname = ANY (deletable) THEN
                    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE %I TO cm_runtime', t.relname);
                ELSE
                    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE %I TO cm_runtime', t.relname);
                END IF;
            END LOOP;

            -- cdr schema: SELECT+INSERT on append-only tables; SELECT+INSERT+UPDATE on import_batches.
            GRANT USAGE ON SCHEMA cdr TO cm_runtime;
            FOR t IN SELECT c.oid, c.relname
                     FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                     WHERE n.nspname = 'cdr' AND c.relkind IN ('r', 'p') LOOP
                EXECUTE format('REVOKE ALL ON cdr.%I FROM cm_runtime', t.relname);
                IF EXISTS (
                    SELECT 1 FROM pg_trigger g
                    WHERE g.tgrelid = t.oid
                      AND g.tgname LIKE 'cdr_forbid_change_%'
                ) THEN
                    EXECUTE format('GRANT SELECT, INSERT ON cdr.%I TO cm_runtime', t.relname);
                ELSE
                    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON cdr.%I TO cm_runtime', t.relname);
                END IF;
            END LOOP;
        END $$
    """)


def downgrade() -> None:
    op.execute("REVOKE ALL ON SCHEMA cdr FROM cm_runtime")
    for tbl in ("import_batches",) + _APPEND_ONLY:
        op.execute(f"REVOKE ALL ON cdr.{tbl} FROM cm_runtime")
    # Restore cm_grant_runtime() to public-only version (from migration 0014)
    op.execute("""
        CREATE OR REPLACE FUNCTION cm_grant_runtime() RETURNS void LANGUAGE plpgsql AS $$
        DECLARE
            t record;
            deletable text[] := ARRAY[
                'document_pages', 'document_chunks', 'document_provisions',
                'case_events', 'case_entities', 'uploads', 'upload_chunks',
                'case_access_grants', 'audit_events', 'user_mfa'
            ];
        BEGIN
            GRANT USAGE ON SCHEMA public TO cm_runtime;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cm_runtime;
            FOR t IN SELECT c.oid, c.relname
                     FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                     WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') LOOP
                EXECUTE format('REVOKE ALL ON TABLE %I FROM cm_runtime', t.relname);
                IF t.relname = 'alembic_version' THEN
                    EXECUTE format('GRANT SELECT ON TABLE %I TO cm_runtime', t.relname);
                ELSIF EXISTS (
                    SELECT 1 FROM pg_trigger g
                    WHERE g.tgrelid = t.oid
                      AND g.tgname = 'cm_' || t.relname || '_permanent'
                      AND t.relname <> 'audit_events'
                ) THEN
                    EXECUTE format('GRANT SELECT, INSERT ON TABLE %I TO cm_runtime', t.relname);
                ELSIF t.relname = ANY (deletable) THEN
                    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE %I TO cm_runtime', t.relname);
                ELSE
                    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE %I TO cm_runtime', t.relname);
                END IF;
            END LOOP;
        END $$
    """)
