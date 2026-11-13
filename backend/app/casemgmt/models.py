"""Case Management tables (docs/case-management/05-database-er.md).

Each class says which kind it is; migration 0007 enforces it with database triggers:
- APPEND-ONLY: rows are never updated or deleted.
- STATUS-ONLY: rows are never deleted; only the named status-like columns change, each change with an event.
"""

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.casemgmt.enums import (
    ArtifactType,
    AuthorizationChange,
    CheckpointReason,
    CommentTarget,
    CustodyEventType,
    FileCategory,
    FileStatus,
    HistoryKind,
    ImportItemType,
    IndicatorType,
    IntegrityResult,
    IntegrityTrigger,
    JobStatus,
    LinkType,
    MemberRole,
    OrgRole,
    PolicyStatus,
    Priority,
    ReportCheckMethod,
    ReportCheckResult,
    ReportType,
    RetentionAction,
    RetentionStatus,
    SourceEventType,
    SourceKind,
    SourceStatus,
    StationStatus,
    StatusField,
    TaskStatus,
    TextSourceKind,
    TextStatus,
    WorkflowStatus,
)
from app.core.enums import Sensitivity
from app.db.base import Base, in_check

SHA256 = String(64)
EMPTY_JSON_LIST = text("'[]'::jsonb")
EMPTY_JSON_OBJECT = text("'{}'::jsonb")
SQL_FALSE = text("false")


def _now_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Organization(Base):
    """A police organisation (tenant). Every case belongs to one; users see only their own organisation's cases.

    Never deleted. The name may change; the code (case-number prefix) only until the first case (migration 0008).
    """

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(8), unique=True)  # the case-ID prefix, e.g. "KH"
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = _now_column()


class PoliceStation(Base):
    """A police station of an organisation. STATUS-ONLY: never deleted; name, district and status may change (code never)."""

    __tablename__ = "police_stations"
    __table_args__ = (UniqueConstraint("organization_id", "code"), in_check("status", StationStatus))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    code: Mapped[str] = mapped_column(String(16))  # short and permanent, e.g. "HQ", "PS-014"
    name: Mapped[str] = mapped_column(String(200))
    district: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default=StationStatus.ACTIVE.value, server_default=StationStatus.ACTIVE.value)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # empty for the station migration 0016 made
    created_at: Mapped[datetime] = _now_column()


class UserStation(Base):
    """Which station a user may see (an Administrator several, a Supervisor or Investigator one; a Super Admin needs none).
    STATUS-ONLY: only revoked_by / revoked_at change, so the history of who could see which station is kept."""

    __tablename__ = "user_stations"
    __table_args__ = (Index("uq_user_stations_active", "user_id", "station_id", unique=True, postgresql_where=text("revoked_at IS NULL")),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    station_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("police_stations.id"), index=True)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = _now_column()
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OfficerRegistry(Base):
    """The list of real officers. An account can be made only for an officer in this list (each officer once).
    STATUS-ONLY: never deleted; station, rank and highest_role change when an officer is transferred or promoted."""

    __tablename__ = "officer_registry"
    __table_args__ = (UniqueConstraint("organization_id", "officer_number"), in_check("highest_role", OrgRole))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    officer_number: Mapped[str] = mapped_column(String(32))  # the officer's ID (collar / badge / service number)
    full_name: Mapped[str] = mapped_column(String(200))
    rank: Mapped[str] = mapped_column(String(64))
    station_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("police_stations.id"), index=True)
    highest_role: Mapped[str] = mapped_column(String(16))  # the highest role an account for this officer may have
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _now_column()


class CaseFamily(Base):
    """One investigation for its whole life. STATUS-ONLY: workflow_status, official_status, supervisor_id, and display_id (the case number:
    every change is recorded in case_number_changes)."""

    __tablename__ = "case_families"
    __table_args__ = (
        UniqueConstraint("organization_id", "display_id"),
        UniqueConstraint("organization_id", "year", "sequence"),
        in_check("classification", Sensitivity),
        in_check("priority", Priority),
        in_check("workflow_status", WorkflowStatus),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    station_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("police_stations.id"), index=True)  # set once, at creation
    display_id: Mapped[str] = mapped_column(String(32))  # e.g. KH-2026-0001: not an official reference
    year: Mapped[int] = mapped_column(Integer)
    sequence: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    case_type: Mapped[str] = mapped_column(String(64))  # any type: see case_types.py
    description: Mapped[str] = mapped_column(Text)
    description_html: Mapped[str | None] = mapped_column(Text)  # the styled copy of the description, cleaned (rich_text.py); reports and search read `description`
    reported_by_unknown: Mapped[bool] = mapped_column(default=False)  # no one was there to report it: the reporter is unknown
    reported_by_name: Mapped[str | None] = mapped_column(String(200))  # who reported the case: all optional, written once at registration
    reported_by_phone: Mapped[str | None] = mapped_column(String(40))
    reported_by_email: Mapped[str | None] = mapped_column(String(200))
    reported_by_address: Mapped[str | None] = mapped_column(String(500))
    priority: Mapped[str] = mapped_column(String(16))
    classification: Mapped[str] = mapped_column(String(16))
    jurisdiction: Mapped[str | None] = mapped_column(String(200))
    supervisor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _now_column()
    workflow_status: Mapped[str] = mapped_column(String(32))
    official_status: Mapped[str | None] = mapped_column(String(64))


class CaseOfficialReference(Base):
    """An official reference (FIR, complaint, court case number). APPEND-ONLY. Never used as the case's ID."""

    __tablename__ = "case_official_references"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    ref_type: Mapped[str] = mapped_column(String(32))
    number: Mapped[str] = mapped_column(String(64))
    issuing_authority: Mapped[str | None] = mapped_column(String(200))
    ref_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(64), default="manual", server_default="manual")
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = _now_column()


class CaseNumberChange(Base):
    """A change of a case's number (KH-2026-0001 -> ...), made by whoever oversees the case. APPEND-ONLY: the old number stays here, so it
    finds the case and is never given to another one (docs/case-management/13 section 12, decision 20)."""

    __tablename__ = "case_number_changes"
    __table_args__ = (Index("ix_case_number_changes_old", "organization_id", "old_number"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    old_number: Mapped[str] = mapped_column(String(32))
    new_number: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = _now_column()


class CaseStatusEvent(Base):
    """Every change of one of the four statuses. APPEND-ONLY."""

    __tablename__ = "case_status_events"
    __table_args__ = (in_check("field", StatusField),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    field: Mapped[str] = mapped_column(String(16))
    old_value: Mapped[str | None] = mapped_column(String(64))
    new_value: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = _now_column()


class CaseFolder(Base):
    """A folder of a case. APPEND-ONLY: made when the case is registered (from its type) or added later; never renamed or removed.

    `system` folders (reports, imports, links) are made by the application the first time something of that kind is added.
    """

    __tablename__ = "case_folders"
    __table_args__ = (Index("uq_case_folders_name", "case_family_id", text("lower(name)"), unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    system: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    added_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    added_at: Mapped[datetime] = _now_column()


class CaseMember(Base):
    """A person's part in one case. STATUS-ONLY: revoked_by, revoked_at (what the person did stays attributed to them).

    At most one active row per person and case, and one active lead per case. Added directly by the case's Investigator
    or Supervisor: there is no invitation to accept.
    """

    __tablename__ = "case_members"
    __table_args__ = (
        Index("uq_case_members_one_active", "case_family_id", "user_id", unique=True, postgresql_where=text("revoked_at IS NULL")),
        Index("uq_case_members_one_lead", "case_family_id", unique=True, postgresql_where=text("role = 'lead' AND revoked_at IS NULL")),
        in_check("role", MemberRole),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    granted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    granted_at: Mapped[datetime] = _now_column()
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CaseEntry(Base):
    """One entry of a case's history. APPEND-ONLY. The entries of a case form a chain: each holds the fingerprint of the one before it
    (prev_hash), so changing, removing or reordering an entry is detected by history.verify_chain. The database itself only accepts
    the next entry in order (trigger cm_case_entries_in_order)."""

    __tablename__ = "case_entries"
    __table_args__ = (UniqueConstraint("case_family_id", "seq"), in_check("kind", HistoryKind))

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)  # 1, 2, 3... per case
    kind: Mapped[str] = mapped_column(String(24))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # set by the server in Python; part of the fingerprint
    subject_type: Mapped[str | None] = mapped_column(String(24))  # "artifact", "evidence", "folder", "user"...
    subject_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=EMPTY_JSON_OBJECT)
    prev_hash: Mapped[str | None] = mapped_column(SHA256)  # None for the first entry
    entry_hash: Mapped[str] = mapped_column(SHA256)


class Artifact(Base):
    """A note, analysis, summary… as a whole, in one folder of the case; its content is in its versions.

    STATUS-ONLY: only the seal fields and the withdrawn fields change (a wrong file is withdrawn with a reason, never deleted);
    each change has a history entry.
    """

    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("case_family_id", "display_id"), in_check("artifact_type", ArtifactType), in_check("status", FileStatus))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    display_id: Mapped[str] = mapped_column(String(32))  # e.g. NOTE-0003
    artifact_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _now_column()
    folder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_folders.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default=FileStatus.ACTIVE.value, server_default=FileStatus.ACTIVE.value)
    withdrawn_reason: Mapped[str | None] = mapped_column(Text)
    withdrawn_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sealed: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    sealed_reason: Mapped[str | None] = mapped_column(Text)
    sealed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ArtifactVersion(Base):
    """One version of an artifact. APPEND-ONLY: editing creates a new version."""

    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint("artifact_id", "version_number"),
        # "Which analyses were derived from this exhibit?" (derived_from holds version IDs).
        Index("ix_artifact_versions_derived_from", "derived_from", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_sha256: Mapped[str] = mapped_column(SHA256)
    derived_from: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _now_column()
    change_note: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- evidence (phase CM-2, docs/case-management/04 §3-4)


class EvidenceObject(Base):
    """The bytes of a file, stored once per SHA-256 in the write-once evidence store (storage.py). APPEND-ONLY."""

    __tablename__ = "evidence_objects"

    sha256: Mapped[str] = mapped_column(SHA256, primary_key=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(100))  # detected from the bytes
    storage_backend: Mapped[str] = mapped_column(String(16))
    storage_key: Mapped[str] = mapped_column(String(300))
    stored_at: Mapped[datetime] = _now_column()


class EvidenceItem(Base):
    """An original exhibit, in one folder of the case. STATUS-ONLY: the seal fields and the withdrawn fields (each change with a history entry
    and, for sealing, a custody event)."""

    __tablename__ = "evidence_items"
    __table_args__ = (
        UniqueConstraint("case_family_id", "display_id"),
        in_check("category", FileCategory),
        in_check("status", FileStatus),
        in_check("classification", Sensitivity),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    display_id: Mapped[str] = mapped_column(String(32))  # EV-0001, per case
    title: Mapped[str] = mapped_column(String(300))
    evidence_type: Mapped[str] = mapped_column(String(64))  # any code: case_types.EVIDENCE_TYPES are suggestions
    category: Mapped[str] = mapped_column(String(16))
    classification: Mapped[str] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(300))  # where it came from, e.g. "complainant's phone"
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_tz: Mapped[str | None] = mapped_column(String(6))  # the original timezone, e.g. +05:30
    collected_by: Mapped[str | None] = mapped_column(String(200))
    collection_authority: Mapped[str | None] = mapped_column(String(300))  # e.g. seizure memo number
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _now_column()
    folder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_folders.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default=FileStatus.ACTIVE.value, server_default=FileStatus.ACTIVE.value)
    withdrawn_reason: Mapped[str | None] = mapped_column(Text)
    withdrawn_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sealed: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    sealed_reason: Mapped[str | None] = mapped_column(Text)
    sealed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvidenceVersion(Base):
    """The original version of an exhibit: exactly one per item. APPEND-ONLY. Corrections are artifacts, never a v2."""

    __tablename__ = "evidence_versions"
    __table_args__ = (UniqueConstraint("evidence_item_id"), CheckConstraint("version_number = 1", name="original_only"))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_items.id"))
    version_number: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    object_sha256: Mapped[str] = mapped_column(SHA256, ForeignKey("evidence_objects.sha256"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    display_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))  # detected from the bytes
    declared_mime_type: Mapped[str | None] = mapped_column(String(100))  # what the uploading browser claimed
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    active_content: Mapped[bool] = mapped_column(default=False)  # programs, scripts, HTML, SVG: never opened inline
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = _now_column()


class EvidenceSourceReference(Base):
    """Where an exhibit came from in another system (provenance). APPEND-ONLY."""

    __tablename__ = "evidence_source_references"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    evidence_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_versions.id"), index=True)
    source_system: Mapped[str] = mapped_column(String(100))
    source_record_id: Mapped[str | None] = mapped_column(String(200))
    source_hash: Mapped[str | None] = mapped_column(String(128))
    original_reference: Mapped[str | None] = mapped_column(Text)
    imported_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    imported_at: Mapped[datetime] = _now_column()


class CustodyEvent(Base):
    """One event in an exhibit's chain of custody. APPEND-ONLY: corrections are new events."""

    __tablename__ = "chain_of_custody_events"
    __table_args__ = (
        in_check("event_type", CustodyEventType),
        Index("ix_chain_of_custody_events_item", "evidence_item_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_items.id"))
    evidence_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_versions.id"))
    event_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))  # who recorded it
    from_custodian_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    from_custodian_name: Mapped[str | None] = mapped_column(String(200))  # a person or body outside the system
    to_custodian_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    to_custodian_name: Mapped[str | None] = mapped_column(String(200))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # when it happened (UTC)
    occurred_tz: Mapped[str | None] = mapped_column(String(6))  # the timezone it was given in
    recorded_at: Mapped[datetime] = _now_column()
    reason: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(String(100))
    verification_sha256: Mapped[str | None] = mapped_column(SHA256)  # the hash computed at that moment
    related_event_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("chain_of_custody_events.id"))
    authorization_ref: Mapped[str | None] = mapped_column(String(200))
    token_id: Mapped[str | None] = mapped_column(String(64), unique=True)  # a download link works once
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=EMPTY_JSON_OBJECT)


class IntegrityCheck(Base):
    """A re-computation of a stored file's SHA-256. APPEND-ONLY."""

    __tablename__ = "evidence_integrity_checks"
    __table_args__ = (
        in_check("result", IntegrityResult),
        in_check("trigger", IntegrityTrigger),
        Index("ix_evidence_integrity_checks_object", "object_sha256", "checked_at"),
        Index("ix_evidence_integrity_checks_item", "evidence_item_id", "id"),  # live pages (CM-8, stream.py)
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    object_sha256: Mapped[str] = mapped_column(SHA256, ForeignKey("evidence_objects.sha256"))
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_items.id"))
    checked_at: Mapped[datetime] = _now_column()
    checked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    trigger: Mapped[str] = mapped_column(String(16))
    result: Mapped[str] = mapped_column(String(16))
    computed_sha256: Mapped[str | None] = mapped_column(SHA256)  # None when the file is missing


# ---------------------------------------------------------------- access history, tasks, comments

class AuthorizationEvent(Base):
    """A change to who may access a case, or to an account's role, stations or password. APPEND-ONLY: the access history."""

    __tablename__ = "authorization_events"
    __table_args__ = (in_check("change", AuthorizationChange), Index("ix_authorization_events_case", "case_family_id", "id"))

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    case_family_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("case_families.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)  # whose access changed
    change: Mapped[str] = mapped_column(String(32))
    old_value: Mapped[str | None] = mapped_column(String(64))
    new_value: Mapped[str | None] = mapped_column(String(64))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = _now_column()


class InvestigationTask(Base):
    """A task on a case's board. STATUS-ONLY: status, assignee_id, version (each change also in task_events)."""

    __tablename__ = "investigation_tasks"
    __table_args__ = (UniqueConstraint("case_family_id", "display_id"), in_check("status", TaskStatus))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    display_id: Mapped[str] = mapped_column(String(32))  # TASK-0001, per case
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _now_column()


class TaskEvent(Base):
    """Every change of a task (created, status, assignee). APPEND-ONLY."""

    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("investigation_tasks.id"), index=True)
    field: Mapped[str] = mapped_column(String(16))
    old_value: Mapped[str | None] = mapped_column(String(64))
    new_value: Mapped[str | None] = mapped_column(String(64))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = _now_column()


class Comment(Base):
    """A comment on a case, an exhibit, a note or a task. APPEND-ONLY: an edit is a new comment that replaces it."""

    __tablename__ = "comments"
    __table_args__ = (in_check("target_type", CommentTarget), Index("ix_comments_target", "case_family_id", "target_type", "target_id"))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"))
    target_type: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[str] = mapped_column(String(64))  # a UUID
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _now_column()
    replaces_comment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("comments.id"))


class CaseLink(Base):
    """The index of case links (links.py). APPEND-ONLY.

    The link itself is case content: an artifact of type `link` in the linking case. This row lets the linked case show which cases link to it. Exactly one target: another case, or
    (phase CM-5) a knowledge-base case.
    """

    __tablename__ = "case_links"
    __table_args__ = (
        in_check("link_type", LinkType),
        CheckConstraint("(target_family_id IS NULL) <> (knowledge_case_id IS NULL)", name="one_target"),
        CheckConstraint("target_family_id IS NULL OR target_family_id <> case_family_id", name="not_itself"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)  # the linking case
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id"), unique=True)
    target_family_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("case_families.id"), index=True)
    knowledge_case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"))
    link_type: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _now_column()


class Notification(Base):
    """A notice for one user. STATUS-ONLY: read_at."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user", "user_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(48))
    case_family_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("case_families.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=EMPTY_JSON_OBJECT)
    created_at: Mapped[datetime] = _now_column()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CaseMessage(Base):
    """A message between people on a case's team: to the whole team (recipient empty) or privately to one member. PERMANENT: it is never
    edited or deleted; who wrote it is always known (docs/case-management/13 section 12)."""

    __tablename__ = "case_messages"
    __table_args__ = (
        Index("ix_case_messages_case", "case_family_id", "id"),
        Index("ix_case_messages_direct", "case_family_id", "sender_id", "recipient_id", "id"),
        CheckConstraint("char_length(btrim(body)) BETWEEN 1 AND 4000", name="body_length"),
        CheckConstraint("recipient_id IS NULL OR recipient_id <> sender_id", name="not_to_oneself"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _now_column()


class CaseChatRead(Base):
    """How far one person has read one conversation of one case ("group" or the other person's id). The only part of the chat that changes."""

    __tablename__ = "case_chat_reads"
    __table_args__ = (UniqueConstraint("user_id", "case_family_id", "thread"),)  # one row per person, case and conversation

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"))
    thread: Mapped[str] = mapped_column(String(40))
    last_read_id: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    updated_at: Mapped[datetime] = _now_column()


class IdempotencyKey(Base):
    """The first answer to a create request sent with an Idempotency-Key, so a repeat returns it instead of a duplicate. APPEND-ONLY."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    key: Mapped[str] = mapped_column(String(100))
    endpoint: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(SHA256)
    status_code: Mapped[int] = mapped_column(Integer)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now_column()


# ---------------------------------------------------------------- Case Intelligence inside cases (phase CM-5, docs/case-management/04 §10)

# Must equal the embedding model's output size, as for the knowledge base (app/db/models.py, document_chunks).
EMBEDDING_DIM = 384
_TEXT_KEY = ["source_kind", "sha256"]


class ObjectText(Base):
    """The text of one content, read once (Case Intelligence's index). APPEND-ONLY.

    Keyed by what it was made from and that content's SHA-256: an exhibit's bytes, or a note's content. The same
    file in two cases is read and indexed once and shared. Who may *see* it is decided per request from the case
    the user asked about (intelligence/scope.py), never stored here.
    """

    __tablename__ = "object_texts"
    __table_args__ = (in_check("source_kind", TextSourceKind), in_check("status", TextStatus))

    source_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    sha256: Mapped[str] = mapped_column(SHA256, primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    extractor: Mapped[str | None] = mapped_column(String(64))  # library and version, for provenance
    page_count: Mapped[int | None] = mapped_column(Integer)  # None for formats without fixed pages
    char_count: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer)
    scanned_pages: Mapped[list[int]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)
    # Statutory provisions found automatically: [{"key", "label", "act", "kind", "number", "mentions", "pages"}]
    provisions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)
    processed_at: Mapped[datetime] = _now_column()


class ObjectPage(Base):
    """The cleaned text of one page (timelines and citations read it). APPEND-ONLY."""

    __tablename__ = "object_pages"
    __table_args__ = (
        UniqueConstraint("source_kind", "sha256", "page_index"),
        ForeignKeyConstraint(_TEXT_KEY, ["object_texts.source_kind", "object_texts.sha256"]),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(16))
    sha256: Mapped[str] = mapped_column(SHA256)
    page_index: Mapped[int] = mapped_column(Integer)  # reading order, from 0
    page_number: Mapped[int | None] = mapped_column(Integer)  # 1-based for PDFs; None for formats without pages
    text: Mapped[str] = mapped_column(Text)
    needs_ocr: Mapped[bool] = mapped_column(default=False, server_default=SQL_FALSE)


class ObjectChunk(Base):
    """A passage, the unit of search inside a case. STATUS-ONLY: embedding, embedding_model.

    Its text never changes; its meaning vector can be added later (the model wasn't loaded) or recomputed by a
    newer model, as for the knowledge base's passages.
    """

    __tablename__ = "object_chunks"
    __table_args__ = (
        UniqueConstraint("source_kind", "sha256", "chunk_index"),
        ForeignKeyConstraint(_TEXT_KEY, ["object_texts.source_kind", "object_texts.sha256"]),
        Index("ix_object_chunks_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_object_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"embedding": "vector_cosine_ops"}),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(16))
    sha256: Mapped[str] = mapped_column(SHA256)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    search_vector: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(128))


# ---------------------------------------------------------------- integrations (phase CM-6, docs/case-management/09)


class IntegrationSource(Base):
    """An outside system allowed to add findings to cases (Log Analyzer, CDR/IPDR, OSINT, alerts…), with its access policy.

    STATUS-ONLY: status, key_hash, key_prefix, key_issued_at; each change has an integration_source_events row.
    The policy can't be edited: a source with a different policy is registered as a new source, so every import
    names the exact policy it was accepted under. The key itself is shown once and never stored (only its SHA-256).
    """

    __tablename__ = "integration_sources"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        in_check("kind", SourceKind),
        in_check("status", SourceStatus),
        in_check("min_case_classification", Sensitivity),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    code: Mapped[str] = mapped_column(String(64))  # e.g. "log-analyzer": part of the imports' paths
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    legal_basis: Mapped[str | None] = mapped_column(Text)  # under what authority the source's data is obtained
    allowed_item_types: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)
    authority_required_for: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)
    min_case_classification: Mapped[str] = mapped_column(String(16))  # imports go only to cases classified at least this
    fictional: Mapped[bool] = mapped_column(default=False, server_default=SQL_FALSE)  # the built-in fictional test source
    status: Mapped[str] = mapped_column(String(16), default=SourceStatus.ENABLED.value)
    key_hash: Mapped[str] = mapped_column(SHA256, unique=True)
    key_prefix: Mapped[str] = mapped_column(String(16))  # the key's first characters, to recognise it
    key_issued_at: Mapped[datetime] = _now_column()
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _now_column()


class IntegrationSourceEvent(Base):
    """A change to an integration source: registered, disabled, enabled, key rotated. APPEND-ONLY."""

    __tablename__ = "integration_source_events"
    __table_args__ = (in_check("event_type", SourceEventType), Index("ix_integration_source_events_source", "source_id", "id"))

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integration_sources.id"))
    event_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    key_prefix: Mapped[str | None] = mapped_column(String(16))  # the key issued by this event, if any
    occurred_at: Mapped[datetime] = _now_column()


class IntegrationImport(Base):
    """One finding received from an outside system and added to a case: its provenance. APPEND-ONLY.

    The finding itself is case content: an artifact of type `import` in the case's "imports" folder. A record its source later changed (a different source hash) becomes a new version of
    the same artifact, with a row of its own here; earlier versions never change.
    """

    __tablename__ = "integration_imports"
    __table_args__ = (
        in_check("item_type", ImportItemType),
        Index("ix_integration_imports_record", "case_family_id", "source_id", "source_record_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integration_sources.id"), index=True)
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id"), index=True)
    artifact_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifact_versions.id"), unique=True)
    item_type: Mapped[str] = mapped_column(String(16))
    source_record_id: Mapped[str] = mapped_column(String(200))
    source_hash: Mapped[str] = mapped_column(String(140))  # "sha256:<hex>", as the source computed it
    payload_ref: Mapped[str | None] = mapped_column(String(500))  # where the full record stays, in the source system
    authority_ref: Mapped[str | None] = mapped_column(String(300))  # the legal authorisation it was obtained under
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # when it happened (UTC)
    observed_tz: Mapped[str | None] = mapped_column(String(6))
    observed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # the end of a period (CDR, IPDR)
    key_prefix: Mapped[str | None] = mapped_column(String(16))  # the source key that sent it; None for the test source
    imported_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))  # the person it was added for
    imported_at: Mapped[datetime] = _now_column()


class IntegrationIndicator(Base):
    """An identifier named by an imported finding (IP, domain, phone, IMEI, IMSI…), to match it across cases. APPEND-ONLY."""

    __tablename__ = "integration_indicators"
    __table_args__ = (
        in_check("indicator_type", IndicatorType),
        UniqueConstraint("import_id", "indicator_type", "value"),
        Index("ix_integration_indicators_value", "organization_id", "indicator_type", "value"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integration_imports.id"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"))
    indicator_type: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(String(300))  # normalised (indicators.py)
    created_at: Mapped[datetime] = _now_column()


# ---------------------------------------------------------------- reports and governance (phase CM-7, docs/case-management/04 §8-9)


class ReportExport(Base):
    """A PDF report generated for a case as of one history entry: the file's SHA-256 and where it is kept. APPEND-ONLY.

    The report is case content too: a version of an artifact of type `report` (RPT-0001 v2), whose content holds the
    same hash, so the case history itself vouches for the file.
    """

    __tablename__ = "report_exports"
    __table_args__ = (in_check("report_type", ReportType),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    subject_entry_seq: Mapped[int] = mapped_column(Integer)  # the state it describes: the case as of this history entry
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifacts.id"), index=True)
    artifact_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifact_versions.id"), unique=True)
    report_type: Mapped[str] = mapped_column(String(32))
    purpose: Mapped[str] = mapped_column(Text)
    file_format: Mapped[str] = mapped_column(String(8), default="pdf")
    sha256: Mapped[str] = mapped_column(SHA256, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    page_count: Mapped[int] = mapped_column(Integer)
    storage_backend: Mapped[str] = mapped_column(String(16))
    storage_key: Mapped[str] = mapped_column(String(300))
    withheld_entries: Mapped[int] = mapped_column(Integer, default=0)
    generated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    generated_at: Mapped[datetime] = _now_column()


class ReportVerification(Base):
    """A check of a report file against its recorded hash: the stored copy, or a copy someone submitted. APPEND-ONLY."""

    __tablename__ = "report_verifications"
    __table_args__ = (in_check("method", ReportCheckMethod), in_check("result", ReportCheckResult),
                      Index("ix_report_verifications_report", "report_export_id", "id"))

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    report_export_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("report_exports.id"))  # None: matches no report
    method: Mapped[str] = mapped_column(String(16))
    result: Mapped[str] = mapped_column(String(16))
    computed_sha256: Mapped[str | None] = mapped_column(SHA256)
    checked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    checked_at: Mapped[datetime] = _now_column()


class ReportDownload(Base):
    """A report file handed out through a one-time link: the export log. APPEND-ONLY."""

    __tablename__ = "report_downloads"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    report_export_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_exports.id"), index=True)
    token_id: Mapped[str] = mapped_column(String(64), unique=True)  # a link works once
    downloaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    downloaded_at: Mapped[datetime] = _now_column()
    verified_sha256: Mapped[str | None] = mapped_column(SHA256)  # the file's hash, checked just before sending it


class AuditCheckpoint(Base):
    """A signed record of the audit chain at one point, also kept as a file in the write-once store. APPEND-ONLY.

    The signature is an HMAC with a key kept outside the database (settings.cm_checkpoint_key): someone who edits the
    database can recompute the chain's hashes, but not a valid checkpoint.
    """

    __tablename__ = "audit_checkpoints"
    __table_args__ = (in_check("reason", CheckpointReason),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    chain_seq: Mapped[int] = mapped_column(BigInteger, unique=True)
    chain_hash: Mapped[str] = mapped_column(SHA256)
    signature: Mapped[str] = mapped_column(SHA256)  # HMAC-SHA256, hexadecimal
    key_id: Mapped[str] = mapped_column(String(16))  # which key signed it (a fingerprint of the key, not the key)
    reason: Mapped[str] = mapped_column(String(16))
    stored_sha256: Mapped[str] = mapped_column(SHA256)  # the checkpoint file in the write-once store
    storage_key: Mapped[str] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # None: the scheduled job
    created_at: Mapped[datetime] = _now_column()


class LegalHold(Base):
    """A legal hold on a case: while it is active, the case can't be archived and no retention decision can be approved.

    STATUS-ONLY: released_by, released_at, release_reason. A hold is never removed: it is released, with a reason.
    """

    __tablename__ = "legal_holds"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    authority_ref: Mapped[str | None] = mapped_column(String(300))  # the order or instruction it follows
    placed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    placed_at: Mapped[datetime] = _now_column()
    released_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_reason: Mapped[str | None] = mapped_column(Text)


class RetentionPolicy(Base):
    """How long closed cases are kept before their retention is reviewed. STATUS-ONLY: status (active or retired)."""

    __tablename__ = "retention_policies"
    __table_args__ = (UniqueConstraint("organization_id", "code"), in_check("status", PolicyStatus))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    review_after_years: Mapped[int] = mapped_column(Integer)  # after the case is closed
    case_types: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=EMPTY_JSON_LIST)  # empty: every type
    legal_basis: Mapped[str] = mapped_column(Text)  # the rule or schedule the policy follows
    status: Mapped[str] = mapped_column(String(16), default=PolicyStatus.ACTIVE.value)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _now_column()


class RetentionDecision(Base):
    """A formal retention decision about one case: proposed by one person, decided by another (two-person rule).

    STATUS-ONLY: status, decided_by, decided_at, decision_note. Nothing in Knight Hawk is ever deleted: an approved
    disposal is a recorded decision for the organisation's own formal process.
    """

    __tablename__ = "retention_decisions"
    __table_args__ = (in_check("action", RetentionAction), in_check("status", RetentionStatus),
                      CheckConstraint("decided_by IS NULL OR decided_by <> proposed_by", name="two_people"))

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    case_family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_families.id"), index=True)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("retention_policies.id"))
    action: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    review_on: Mapped[date | None] = mapped_column(Date)  # for "retain": when to review again
    transfer_to: Mapped[str | None] = mapped_column(String(300))  # for "transfer": to whom
    proposed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    proposed_at: Mapped[datetime] = _now_column()
    status: Mapped[str] = mapped_column(String(16), default=RetentionStatus.PROPOSED.value)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)


class JobRun(Base):
    """One run of a scheduled job of the worker (scripts/worker.py), or of the same check started by hand. APPEND-ONLY."""

    __tablename__ = "job_runs"
    __table_args__ = (in_check("status", JobStatus), Index("ix_job_runs_job", "job", "started_at"))

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = _now_column()
    status: Mapped[str] = mapped_column(String(16))
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=EMPTY_JSON_OBJECT)
    started_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))  # None: the worker


# Tables whose rows can never change or be deleted, and those that can only change status (migrations 0007, 0009-0014).
APPEND_ONLY_TABLES = (
    "case_official_references", "case_status_events", "case_folders", "case_entries", "artifact_versions",
    "evidence_objects", "evidence_versions", "evidence_source_references", "chain_of_custody_events",
    "evidence_integrity_checks", "authorization_events", "task_events", "comments", "idempotency_keys",
    "case_links", "object_texts", "object_pages",
    "integration_source_events", "integration_imports", "integration_indicators",
    "report_exports", "report_verifications", "report_downloads", "audit_checkpoints", "job_runs",
)
NO_DELETE_TABLES = (
    "organizations", "case_families", "case_members", "evidence_items", "artifacts",
    "investigation_tasks", "notifications", "object_chunks",
    "integration_sources", "legal_holds", "retention_policies", "retention_decisions",
    "police_stations", "user_stations", "officer_registry",
)
