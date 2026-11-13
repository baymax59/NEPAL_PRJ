"""CDR Analysis schema: import batches, normalized records, custody events.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-12

The CDR module lives in schema `cdr`, separate from `public`, so Knight Hawk's
existing triggers and permissions are unaffected. Tables are append-only or
status-only (no row is ever deleted; custody_events and records are never updated).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS cdr")

    # ------------------------------------------------------------------ import_batches (STATUS-ONLY)
    op.create_table(
        "import_batches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("case_family_id", UUID(as_uuid=True), sa.ForeignKey("case_families.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uploaded_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("file_name", sa.Text, nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("file_hash_sha256", sa.Text, nullable=False),
        sa.Column("file_path", sa.Text, nullable=True),
        sa.Column("record_format", sa.Text, nullable=False),
        sa.Column("msisdn_rule", sa.Text, nullable=False),
        sa.Column("source_timezone", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("total_rows", sa.Integer, nullable=True),
        sa.Column("accepted_rows", sa.Integer, nullable=True),
        sa.Column("rejected_rows", sa.Integer, nullable=True),
        sa.Column("duplicate_rows", sa.Integer, nullable=True),
        sa.Column("import_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("file_size_bytes > 0", name="cdr_import_batches_size_positive"),
        sa.CheckConstraint("length(file_hash_sha256) = 64", name="cdr_import_batches_hash_len"),
        sa.CheckConstraint("record_format IN ('csv','xls','xlsx')", name="cdr_import_batches_format"),
        sa.CheckConstraint("msisdn_rule IN ('np-msisdn.v1','in-msisdn.v1')", name="cdr_import_batches_rule"),
        sa.CheckConstraint("status IN ('pending','processing','completed','completed_with_errors','failed')", name="cdr_import_batches_status"),
        sa.Index("ix_cdr_import_batches_case", "case_family_id"),
        sa.Index("ix_cdr_import_batches_user", "uploaded_by"),
        schema="cdr",
    )

    # ------------------------------------------------------------------ records (APPEND-ONLY)
    op.create_table(
        "records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("import_batch_id", UUID(as_uuid=True), sa.ForeignKey("cdr.import_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("case_family_id", UUID(as_uuid=True), sa.ForeignKey("case_families.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_row_number", sa.Integer, nullable=False),
        sa.Column("record_fingerprint", sa.Text, nullable=False),
        sa.Column("is_duplicate", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("a_party", sa.Text, nullable=True),
        sa.Column("b_party", sa.Text, nullable=True),
        sa.Column("a_party_canonical", sa.Text, nullable=True),
        sa.Column("b_party_canonical", sa.Text, nullable=True),
        sa.Column("msisdn_rule", sa.Text, nullable=True),
        sa.Column("timestamp_local", sa.DateTime(timezone=False), nullable=True),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timestamp_tz_source", sa.Text, nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("call_type", sa.Text, nullable=True),
        sa.Column("call_direction", sa.Text, nullable=True),
        sa.Column("service_type", sa.Text, nullable=True),
        sa.Column("imei", sa.Text, nullable=True),
        sa.Column("imsi", sa.Text, nullable=True),
        sa.Column("cell_id", sa.Text, nullable=True),
        sa.Column("area_code", sa.Text, nullable=True),
        sa.Column("operator", sa.Text, nullable=True),
        sa.Column("network_type", sa.Text, nullable=True),
        sa.Column("network_generation", sa.Text, nullable=True),
        sa.Column("date_range_status", sa.Text, nullable=True),
        sa.Column("source_values", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("source_row_number >= 1", name="cdr_records_row_positive"),
        sa.CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="cdr_records_duration"),
        sa.CheckConstraint("call_direction IS NULL OR call_direction IN ('incoming','outgoing')", name="cdr_records_direction"),
        sa.CheckConstraint("service_type IS NULL OR service_type IN ('voice','sms','data')", name="cdr_records_service"),
        sa.CheckConstraint("network_generation IS NULL OR network_generation IN ('2G','3G','4G','5G')", name="cdr_records_gen"),
        sa.CheckConstraint("length(record_fingerprint) = 64", name="cdr_records_fp_len"),
        sa.UniqueConstraint("import_batch_id", "source_row_number", name="uq_cdr_records_batch_row"),
        sa.Index("ix_cdr_records_case_ts", "case_family_id", "timestamp_utc"),
        sa.Index("ix_cdr_records_case_a", "case_family_id", "a_party_canonical"),
        sa.Index("ix_cdr_records_case_b", "case_family_id", "b_party_canonical"),
        sa.Index("ix_cdr_records_batch", "import_batch_id"),
        sa.Index("ix_cdr_records_fp", "case_family_id", "record_fingerprint"),
        schema="cdr",
    )

    # ------------------------------------------------------------------ custody_events (APPEND-ONLY)
    op.create_table(
        "custody_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("import_batch_id", UUID(as_uuid=True), sa.ForeignKey("cdr.import_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("actor_type", sa.Text, nullable=False, server_default="system"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "event_type IN ('received','hashed','stored','processing_started','processing_completed',"
            "'processing_failed','integrity_verified','integrity_failed')",
            name="cdr_custody_events_type",
        ),
        sa.CheckConstraint("actor_type IN ('user','system')", name="cdr_custody_events_actor_type"),
        sa.Index("ix_cdr_custody_events_batch", "import_batch_id"),
        schema="cdr",
    )

    # ------------------------------------------------------------------ validation_errors (APPEND-ONLY)
    op.create_table(
        "validation_errors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("import_batch_id", UUID(as_uuid=True), sa.ForeignKey("cdr.import_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_row_number", sa.Integer, nullable=True),
        sa.Column("field", sa.Text, nullable=True),
        sa.Column("severity", sa.Text, nullable=False, server_default="error"),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("severity IN ('error','warning')", name="cdr_validation_errors_severity"),
        sa.Index("ix_cdr_validation_errors_batch", "import_batch_id"),
        schema="cdr",
    )

    # ------------------------------------------------------------------ permanence triggers
    for tbl in ("custody_events", "records"):
        op.execute(f"""
            CREATE OR REPLACE FUNCTION cdr_forbid_change_{tbl}()
            RETURNS TRIGGER LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'cdr.{tbl} is append-only: updates and deletes are not allowed';
            END;
            $$
        """)
        op.execute(f"""
            CREATE TRIGGER cdr_forbid_change_{tbl}
            BEFORE UPDATE OR DELETE ON cdr.{tbl}
            FOR EACH ROW EXECUTE FUNCTION cdr_forbid_change_{tbl}()
        """)

    op.execute("""
        CREATE OR REPLACE FUNCTION cdr_import_batches_status_only()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.id IS DISTINCT FROM NEW.id OR
               OLD.case_family_id IS DISTINCT FROM NEW.case_family_id OR
               OLD.uploaded_by IS DISTINCT FROM NEW.uploaded_by OR
               OLD.file_name IS DISTINCT FROM NEW.file_name OR
               OLD.file_hash_sha256 IS DISTINCT FROM NEW.file_hash_sha256 OR
               OLD.record_format IS DISTINCT FROM NEW.record_format OR
               OLD.msisdn_rule IS DISTINCT FROM NEW.msisdn_rule OR
               OLD.source_timezone IS DISTINCT FROM NEW.source_timezone OR
               OLD.created_at IS DISTINCT FROM NEW.created_at THEN
                RAISE EXCEPTION 'cdr.import_batches: only status, counts, file_path, notes and completed_at may change';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER cdr_import_batches_status_only
        BEFORE UPDATE ON cdr.import_batches
        FOR EACH ROW EXECUTE FUNCTION cdr_import_batches_status_only()
    """)


def downgrade() -> None:
    for tbl in ("custody_events", "records"):
        op.execute(f"DROP TRIGGER IF EXISTS cdr_forbid_change_{tbl} ON cdr.{tbl}")
        op.execute(f"DROP FUNCTION IF EXISTS cdr_forbid_change_{tbl}()")
    op.execute("DROP TRIGGER IF EXISTS cdr_import_batches_status_only ON cdr.import_batches")
    op.execute("DROP FUNCTION IF EXISTS cdr_import_batches_status_only()")
    op.drop_table("validation_errors", schema="cdr")
    op.drop_table("custody_events", schema="cdr")
    op.drop_table("records", schema="cdr")
    op.drop_table("import_batches", schema="cdr")
    op.execute("DROP SCHEMA IF EXISTS cdr")
