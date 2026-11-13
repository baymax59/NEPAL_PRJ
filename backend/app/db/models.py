"""Database tables.

Every data source is mapped into these tables through a connector and the shared
CaseRecord schema (app/schemas/case_record.py). Nothing here is specific to one source;
source-only fields go into `source_extra`.

NULL always means "the source does not say". Never store a guess in these columns.
"""

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.casemgmt.enums import OrgRole
from app.core.enums import (
    AuditOutcome,
    EventSource,
    EventType,
    ExtractionStatus,
    ProcessingStatus,
    Role,
    RunStatus,
    Sensitivity,
)
from app.db.base import Base, in_check

# Must equal the output size of the embedding model (BAAI/bge-small-en-v1.5 -> 384).
# Switching to a model with a different size requires a new migration.
EMBEDDING_DIM = 384

EMPTY_JSON_LIST = text("'[]'::jsonb")
EMPTY_JSON_OBJECT = text("'{}'::jsonb")
SQL_FALSE = text("false")


class IngestionRun(Base):
    """One execution of an import, for provenance ("which run brought this record in?")."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (in_check("status", RunStatus),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_system: Mapped[str] = mapped_column(String(64))
    connector_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(16), default=RunStatus.RUNNING.value, server_default=RunStatus.RUNNING.value
    )
    # e.g. {"years": [2023], "limit": 100}
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=EMPTY_JSON_OBJECT)
    # e.g. {"created": 95, "updated": 0, "skipped": 3, "failed": 2}
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=EMPTY_JSON_OBJECT)
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        # The same source record can only be imported once; re-imports update it.
        UniqueConstraint("source_system", "source_record_id"),
        in_check("sensitivity", Sensitivity),
        in_check("processing_status", ProcessingStatus),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    display_id: Mapped[str] = mapped_column(String(64), unique=True)

    # --- Where the record came from ---
    source_system: Mapped[str] = mapped_column(String(64), index=True)
    source_record_id: Mapped[str] = mapped_column(String(256))
    reference_numbers: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default=EMPTY_JSON_OBJECT
    )
    # {"source_uri", "retrieved_at", "connector", "connector_version", "checksum_sha256"}
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=EMPTY_JSON_OBJECT)
    last_ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )

    # --- Core case fields (NULL = not in source) ---
    title: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    court_or_agency: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    # Summary as recorded in the source. AI-generated summaries are stored separately later.
    summary: Mapped[str | None] = mapped_column(Text)

    outcome: Mapped[str | None] = mapped_column(Text)
    outcome_source_field: Mapped[str | None] = mapped_column(Text)
    outcome_date: Mapped[date | None] = mapped_column(Date)

    # The most important date, copied out of `dates` so lists can be sorted and filtered by it.
    primary_date: Mapped[date | None] = mapped_column(Date, index=True)
    primary_date_kind: Mapped[str | None] = mapped_column(String(64))
    # Every known date: [{"kind": "decision", "value": "2023-12-04", "source_field": "decision_date"}]
    dates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)

    # [{"role": "petitioner", "name": "..."}]. May contain personal data for some sources.
    parties: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)
    # [{"role": "judge", "name": "..."}]
    officials: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)

    # Fields specific to one source that don't fit the shared schema.
    source_extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=EMPTY_JSON_OBJECT)

    # --- Access control ---
    sensitivity: Mapped[str] = mapped_column(String(16), index=True)

    # --- Data quality ---
    processing_status: Mapped[str] = mapped_column(
        String(32),
        default=ProcessingStatus.METADATA_IMPORTED.value,
        server_default=ProcessingStatus.METADATA_IMPORTED.value,
    )
    missing_fields: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list["CaseDocument"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseDocument.created_at"
    )
    events: Mapped[list["CaseEvent"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseEvent.event_date"
    )


class CaseDocument(Base):
    """A source file belonging to a case (e.g. a judgment PDF)."""

    __tablename__ = "case_documents"
    __table_args__ = (
        UniqueConstraint("case_id", "source_uri"),
        in_check("extraction_status", ExtractionStatus),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)

    doc_type: Mapped[str] = mapped_column(String(64))  # e.g. "judgment", "fir", "chargesheet"
    title: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(16))
    doc_date: Mapped[date | None] = mapped_column(Date)

    source_uri: Mapped[str] = mapped_column(Text)  # where the original came from
    local_path: Mapped[str | None] = mapped_column(Text)  # where our copy is, relative to the data folder
    mime_type: Mapped[str | None] = mapped_column(String(128))
    sha256: Mapped[str | None] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column(Integer)

    extraction_status: Mapped[str] = mapped_column(
        String(32), default=ExtractionStatus.PENDING.value, server_default=ExtractionStatus.PENDING.value
    )
    extraction_warnings: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=EMPTY_JSON_LIST
    )
    extractor: Mapped[str | None] = mapped_column(String(64))  # e.g. "pypdfium2 5.14.0"
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    case: Mapped[Case] = relationship(back_populates="documents")
    pages: Mapped[list["DocumentPage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentPage.page_number"
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentChunk.chunk_index"
    )


class DocumentPage(Base):
    """Cleaned text of one page, kept so pages can be shown and cited without re-reading the file."""

    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("case_documents.id", ondelete="CASCADE"), index=True
    )
    # NULL for formats without fixed pages (Word, plain text), which are stored as one row.
    page_number: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)
    # Little or no text but contains images: probably scanned, so text is missing until OCR.
    needs_ocr: Mapped[bool] = mapped_column(default=False, server_default=SQL_FALSE)

    document: Mapped[CaseDocument] = relationship(back_populates="pages")


class DocumentChunk(Base):
    """A passage of document text: the unit that keyword and semantic search work on."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        # Keyword search index (Step 5).
        Index("ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"),
        # Semantic search index (Step 6): approximate nearest neighbours by cosine distance.
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("case_documents.id", ondelete="CASCADE"), index=True
    )
    # Duplicated from the document so search can filter by case without an extra join.
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)

    chunk_index: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)

    # Filled in automatically by PostgreSQL whenever `text` changes.
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True)
    )
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[CaseDocument] = relationship(back_populates="chunks")


class DocumentProvision(Base):
    """A statutory provision cited in a document, found automatically (see app/explain/provisions.py)."""

    __tablename__ = "document_provisions"
    __table_args__ = (UniqueConstraint("document_id", "provision_key"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("case_documents.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    provision_key: Mapped[str] = mapped_column(String(200), index=True)  # e.g. "crpc|section|438"
    label: Mapped[str] = mapped_column(Text)  # e.g. "Section 438 CrPC"
    act: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))
    number: Mapped[str] = mapped_column(String(32))
    mention_count: Mapped[int] = mapped_column(Integer)
    # Pages where it is cited (empty for formats without pages).
    pages: Mapped[list[int]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)


class Upload(Base):
    """A new case document uploaded to find similar historical cases.

    Kept apart from `cases` on purpose: an upload is a query, not part of the historical record.
    """

    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(Text)  # for display only, never used as a path
    stored_path: Mapped[str] = mapped_column(Text)  # relative to data_dir
    sha256: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    # [{"key", "label", "mentions", "pages"}]
    provisions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)
    # Who uploaded it. Filled once login exists (Step 10); only the owner may use it then.
    owner_id: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["UploadChunk"]] = relationship(
        back_populates="upload", cascade="all, delete-orphan", order_by="UploadChunk.chunk_index"
    )


class UploadChunk(Base):
    __tablename__ = "upload_chunks"
    __table_args__ = (UniqueConstraint("upload_id", "chunk_index"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(128))

    upload: Mapped[Upload] = relationship(back_populates="chunks")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (in_check("role", Role), in_check("clearance", Sensitivity), in_check("org_role", OrgRole))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)  # stored lower-case
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(Text)  # Argon2; the password itself is never stored
    role: Mapped[str] = mapped_column(String(16))
    # Highest sensitivity level the user may see; see also CaseAccessGrant.
    clearance: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Case Management (Step 15): the user's organisation (tenant) and organisation role. `role` above
    # stays the Case Intelligence role (viewer / analyst / admin).
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    org_role: Mapped[str] = mapped_column(String(16), default=OrgRole.VIEWER.value, server_default=OrgRole.VIEWER.value)
    # A temporary password was handed over (new account, or a reset): the owner must choose their own before anything else.
    must_change_password: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # When the current role took effect (empty = from the start). Powers that come from the role itself reach only cases
    # registered since then: a promotion adds no power over cases that already exist (docs/case-management/12 section 5).
    org_role_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The person's own profile (migration 0023): filled in by them, all optional. Name, officer ID, rank and station come from the register.
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    job_title: Mapped[str | None] = mapped_column(String(100))
    profile_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The profile photo (migration 0024): a small JPEG made by app/auth/photos.py. Loaded only when the picture is asked for.
    photo_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    photo_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The real officer this account belongs to (officer_registry). Empty only for accounts made before migration 0016.
    officer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("officer_registry.id", use_alter=True, name="fk_users_officer_id_officer_registry"), unique=True)


class CaseAccessGrant(Base):
    """Need-to-know access to one case above the user's clearance."""

    __tablename__ = "case_access_grants"
    __table_args__ = (UniqueConstraint("case_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    granted_by: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    """Who did what, when. No foreign keys: the record must outlive users and cases.

    Privacy: search text is never stored, only a keyed fingerprint (see app/audit/log.py).
    """

    __tablename__ = "audit_events"
    __table_args__ = (in_check("outcome", AuditOutcome),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)  # e.g. "case.view", "search"
    outcome: Mapped[str] = mapped_column(String(16))
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=EMPTY_JSON_OBJECT)
    client_ip: Mapped[str | None] = mapped_column(String(64))
    # Case Management events (action "cm.*") form a hash chain (phase CM-7, docs/case-management/04 §8). The database
    # fills these on insert (trigger cm_audit_events_chain); they are never set by the application. Other events stay
    # outside the chain, under their own retention rule (Step 14.3).
    chain_seq: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str | None] = mapped_column(String(64))


class UserMfa(Base):
    """A user's two-step verification (TOTP, phase CM-7). The secret is stored encrypted (app/auth/mfa.py)."""

    __tablename__ = "user_mfa"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    secret_encrypted: Mapped[str] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # set by the first valid code
    last_step: Mapped[int | None] = mapped_column(BigInteger)  # the last 30-second step used: each code works once
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaseEntity(Base):
    """A named thing a document mentions (for now: courts and tribunals), found automatically."""

    __tablename__ = "case_entities"
    __table_args__ = (UniqueConstraint("document_id", "kind", "value"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("case_documents.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # "court"
    value: Mapped[str] = mapped_column(Text)  # e.g. "High Court of Kerala"
    mentions: Mapped[int] = mapped_column(Integer)
    pages: Mapped[list[int]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)


class CaseEvent(Base):
    """One entry on a case timeline, always linked back to where it came from."""

    __tablename__ = "case_events"
    __table_args__ = (in_check("extraction_method", EventSource), in_check("event_type", EventType))

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(
        String(32), default=EventType.OTHER.value, server_default=EventType.OTHER.value
    )

    event_date: Mapped[date | None] = mapped_column(Date)
    # The date exactly as written in the source, e.g. "in or around March 1998".
    date_text: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("case_documents.id", ondelete="SET NULL")
    )
    page_number: Mapped[int | None] = mapped_column(Integer)
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped[Case] = relationship(back_populates="events")


# Case Management tables (Step 15) share this metadata, so migrations and `alembic check` see them.
from app.casemgmt import models as _casemgmt_models  # noqa: E402,F401
