"""Fixed sets of allowed values, shared by the database tables and the Pydantic schemas.

Stored as plain text with CHECK constraints rather than PostgreSQL ENUM types,
because text + CHECK is much easier to change later with a migration.
"""

from enum import StrEnum


class Sensitivity(StrEnum):
    """How restricted a record is. Drives record-level access control (Step 10)."""

    PUBLIC = "public"  # e.g. published court judgments
    INTERNAL = "internal"
    RESTRICTED = "restricted"  # e.g. police records
    CONFIDENTIAL = "confidential"


class ProcessingStatus(StrEnum):
    """How far a case has got through the ingestion pipeline."""

    METADATA_IMPORTED = "metadata_imported"  # Step 3
    TEXT_EXTRACTED = "text_extracted"  # Step 4
    INDEXED = "indexed"  # Step 6: chunks embedded, searchable
    FAILED = "failed"


class ExtractionStatus(StrEnum):
    """Text-extraction state of a single document."""

    PENDING = "pending"
    EXTRACTED = "extracted"
    NEEDS_OCR = "needs_ocr"  # scanned pages with no text layer
    FAILED = "failed"


class EventSource(StrEnum):
    """How a timeline event was obtained, so the UI can label it honestly."""

    SOURCE_FIELD = "source_field"  # copied from a structured source field
    RULE_BASED = "rule_based"  # pattern-matched from document text
    MODEL = "model"  # extracted by an AI model
    MANUAL = "manual"  # entered by a person


class EventType(StrEnum):
    JUDGMENT = "judgment"  # the decision itself (from the source record)
    ORDER_UNDER_APPEAL = "order_under_appeal"  # the lower court's order being challenged
    DATED_MENTION = "dated_mention"  # any other date found in the text, with its sentence
    OTHER = "other"


class Role(StrEnum):
    """What a user may *do*. What they may *see* is decided by clearance and grants."""

    VIEWER = "viewer"  # search, read cases and explanations
    ANALYST = "analyst"  # + upload new cases and find similar ones
    ADMIN = "admin"  # + read the audit log


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"  # exists, but the user may not see it (the user is told "not found")
    NOT_FOUND = "not_found"
    REJECTED = "rejected"  # invalid input or failed login
    ERROR = "error"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"  # finished, but some records failed
    FAILED = "failed"
