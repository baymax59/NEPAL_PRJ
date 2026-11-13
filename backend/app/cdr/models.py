"""SQLAlchemy ORM models for the cdr schema."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CdrImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint("file_size_bytes > 0", name="cdr_import_batches_size_positive"),
        CheckConstraint("length(file_hash_sha256) = 64", name="cdr_import_batches_hash_len"),
        CheckConstraint("record_format IN ('csv','xls','xlsx')", name="cdr_import_batches_format"),
        CheckConstraint("msisdn_rule IN ('np-msisdn.v1','in-msisdn.v1')", name="cdr_import_batches_rule"),
        CheckConstraint("status IN ('pending','processing','completed','completed_with_errors','failed')", name="cdr_import_batches_status"),
        Index("ix_cdr_import_batches_case", "case_family_id"),
        Index("ix_cdr_import_batches_user", "uploaded_by"),
        {"schema": "cdr"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_families.id", ondelete="RESTRICT"), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_format: Mapped[str] = mapped_column(Text, nullable=False)
    msisdn_rule: Mapped[str] = mapped_column(Text, nullable=False)
    source_timezone: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    total_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accepted_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejected_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    import_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CdrRecord(Base):
    __tablename__ = "records"
    __table_args__ = (
        CheckConstraint("source_row_number >= 1", name="cdr_records_row_positive"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="cdr_records_duration"),
        CheckConstraint("call_direction IS NULL OR call_direction IN ('incoming','outgoing')", name="cdr_records_direction"),
        CheckConstraint("service_type IS NULL OR service_type IN ('voice','sms','data')", name="cdr_records_service"),
        CheckConstraint("network_generation IS NULL OR network_generation IN ('2G','3G','4G','5G')", name="cdr_records_gen"),
        CheckConstraint("length(record_fingerprint) = 64", name="cdr_records_fp_len"),
        UniqueConstraint("import_batch_id", "source_row_number", name="uq_cdr_records_batch_row"),
        Index("ix_cdr_records_case_ts", "case_family_id", "timestamp_utc"),
        Index("ix_cdr_records_case_a", "case_family_id", "a_party_canonical"),
        Index("ix_cdr_records_case_b", "case_family_id", "b_party_canonical"),
        Index("ix_cdr_records_batch", "import_batch_id"),
        Index("ix_cdr_records_fp", "case_family_id", "record_fingerprint"),
        {"schema": "cdr"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    import_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cdr.import_batches.id", ondelete="RESTRICT"), nullable=False)
    case_family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_families.id", ondelete="RESTRICT"), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    record_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    a_party: Mapped[str | None] = mapped_column(Text, nullable=True)
    b_party: Mapped[str | None] = mapped_column(Text, nullable=True)
    a_party_canonical: Mapped[str | None] = mapped_column(Text, nullable=True)
    b_party_canonical: Mapped[str | None] = mapped_column(Text, nullable=True)
    msisdn_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    timestamp_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timestamp_tz_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    call_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    imei: Mapped[str | None] = mapped_column(Text, nullable=True)
    imsi: Mapped[str | None] = mapped_column(Text, nullable=True)
    cell_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator: Mapped[str | None] = mapped_column(Text, nullable=True)
    network_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    network_generation: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_range_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CdrCustodyEvent(Base):
    __tablename__ = "custody_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('received','hashed','stored','processing_started','processing_completed',"
            "'processing_failed','integrity_verified','integrity_failed')",
            name="cdr_custody_events_type",
        ),
        CheckConstraint("actor_type IN ('user','system')", name="cdr_custody_events_actor_type"),
        Index("ix_cdr_custody_events_batch", "import_batch_id"),
        {"schema": "cdr"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    import_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cdr.import_batches.id", ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False, default="system")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class CdrValidationError(Base):
    __tablename__ = "validation_errors"
    __table_args__ = (
        CheckConstraint("severity IN ('error','warning')", name="cdr_validation_errors_severity"),
        Index("ix_cdr_validation_errors_batch", "import_batch_id"),
        {"schema": "cdr"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    import_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cdr.import_batches.id", ondelete="RESTRICT"), nullable=False)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    field: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="error")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
