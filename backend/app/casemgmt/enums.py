"""Fixed value lists for Case Management (stored as text, limited by CHECK constraints)."""

from enum import StrEnum


class OrgRole(StrEnum):
    """The seven roles of a user's account (docs/case-management/12-roles-and-stations.md).

    SUPER_ADMIN: every station. ADMINISTRATOR: the stations the Super Admin assigned. SUPERVISOR: one station.
    INVESTIGATOR: their own cases at one station. SUB_INVESTIGATOR and ANALYST: the cases they are added to.
    VIEWER: read only. (SUPER_ADMIN was called platform_admin before migration 0016.)
    """

    SUPER_ADMIN = "super_admin"
    ADMINISTRATOR = "administrator"
    SUPERVISOR = "supervisor"
    INVESTIGATOR = "investigator"
    SUB_INVESTIGATOR = "sub_investigator"
    ANALYST = "analyst"
    VIEWER = "viewer"  # also auditors: read only


class MemberRole(StrEnum):
    """A person's part in one case (docs/case-management/13-plain-case-design.md). LEAD is the case's Investigator; the
    others are added to the case by the Investigator or the Supervisor."""

    LEAD = "lead"
    SUB_INVESTIGATOR = "sub_investigator"
    ANALYST = "analyst"
    VIEWER = "viewer"


class StationStatus(StrEnum):
    """A police station is never deleted; one that no longer works is marked inactive and keeps its history."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class LinkType(StrEnum):
    """How a case is related to another (case links, CM-4). Generic: they fit every type of case."""

    RELATED = "related"
    SAME_PERSON = "same_person"  # the same person of interest
    SAME_VICTIM = "same_victim"  # the same victim or complainant
    SAME_METHOD = "same_method"  # the same modus operandi
    SHARED_EVIDENCE = "shared_evidence"  # an exhibit or indicator (phone number, account, IP address) in both
    SAME_PLACE = "same_place"
    POSSIBLE_DUPLICATE = "possible_duplicate"  # the same incident reported twice
    PART_OF = "part_of"  # this case is part of a larger one


class FileStatus(StrEnum):
    """A file of a case (an exhibit, a note...) is never deleted; a wrong one is withdrawn, with a reason, and stays in the history."""

    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


class HistoryKind(StrEnum):
    """What a history entry of a case records (case_entries). The entries form one chain per case (history.py)."""

    CASE_REGISTERED = "case_registered"
    FOLDER_ADDED = "folder_added"
    NOTE_ADDED = "note_added"  # a note, analysis, transcription or timeline written in the system
    NOTE_REVISED = "note_revised"  # a new version of a note
    EVIDENCE_ADDED = "evidence_added"
    FILE_WITHDRAWN = "file_withdrawn"
    FILE_SEALED = "file_sealed"
    FILE_UNSEALED = "file_unsealed"
    STATUS_CHANGED = "status_changed"  # the workflow or official status of the case
    REFERENCE_ADDED = "reference_added"  # an official reference (FIR number...)
    MEMBER_ADDED = "member_added"
    MEMBER_REMOVED = "member_removed"
    LEAD_CHANGED = "lead_changed"
    CASE_RENUMBERED = "case_renumbered"  # the case number was changed (the old one is kept and still finds the case)
    LINK_ADDED = "link_added"
    IMPORT_ADDED = "import_added"  # a finding received from an outside system
    TIMELINE_GENERATED = "timeline_generated"
    REPORT_GENERATED = "report_generated"


class ArtifactType(StrEnum):
    CASE_SUMMARY = "case_summary"
    OFFICIAL_REFERENCES = "official_references"
    NOTE = "note"
    ANALYSIS = "analysis"
    TRANSCRIPTION = "transcription"
    TIMELINE = "timeline"
    REPORT = "report"
    IMPORT = "import"
    LINK = "link"


class WorkflowStatus(StrEnum):
    REGISTERED = "registered"
    OPEN = "open"
    UNDER_INVESTIGATION = "under_investigation"
    PENDING_EVIDENCE = "pending_evidence"
    PENDING_REVIEW = "pending_review"
    APPROVED_FOR_REPORTING = "approved_for_reporting"
    INVESTIGATION_COMPLETED = "investigation_completed"
    CLOSED = "closed"
    ARCHIVED = "archived"
    REOPENED = "reopened"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StatusField(StrEnum):
    """Which status an event changed (docs/case-management/04 §7)."""

    WORKFLOW = "workflow"
    OFFICIAL = "official"
    SEAL = "seal"  # a note or analysis sealed or unsealed


class FileCategory(StrEnum):
    """What an evidence file is, decided from its bytes (filetypes.py), not from its name."""

    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    ARCHIVE = "archive"
    TEXT = "text"
    DATA = "data"  # databases, packet captures, forensic images
    EXECUTABLE = "executable"  # programs: kept as evidence (e.g. malware), never run or opened
    BINARY = "binary"  # bytes of no recognised type


class CustodyEventType(StrEnum):
    """Chain of custody (docs/case-management/04 §4). A transfer to a person is complete only once acknowledged."""

    COLLECTED = "collected"
    INGESTED = "ingested"
    TRANSFERRED = "transferred"
    ACKNOWLEDGED = "acknowledged"
    DECLINED = "declined"  # a transfer that did not happen (refused by the receiver, or withdrawn by the sender)
    ACCESSED = "accessed"
    VERIFIED = "verified"
    SEALED = "sealed"
    UNSEALED = "unsealed"
    EXPORTED = "exported"  # reports (phase CM-7)


class IntegrityResult(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"  # the stored bytes changed since they were recorded
    MISSING = "missing"  # the stored file is gone


class IntegrityTrigger(StrEnum):
    """Why an integrity check ran."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    DOWNLOAD = "download"
    PREVIEW = "preview"
    ACKNOWLEDGEMENT = "acknowledgement"
    UPLOAD = "upload"  # the same bytes were uploaded again: the stored copy was checked first
    INDEXING = "indexing"  # checked before Case Intelligence read the file's text (CM-5)


# ---------------------------------------------------------------- tasks, comments and access history


class TaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class CommentTarget(StrEnum):
    CASE = "case"
    EVIDENCE = "evidence"
    ARTIFACT = "artifact"
    TASK = "task"


class AuthorizationChange(StrEnum):
    """Changes to who may access what, kept as permanent access history."""

    MEMBERSHIP_GRANTED = "membership_granted"
    MEMBERSHIP_REVOKED = "membership_revoked"
    ACCOUNT_CREATED = "account_created"  # who made the account, with which role (docs/case-management/12)
    ROLE_CHANGED = "role_changed"  # a promotion or demotion: old role, new role
    STATION_GRANTED = "station_granted"
    STATION_REVOKED = "station_revoked"
    PASSWORD_RESET = "password_reset"  # a new temporary password was issued (never recorded: only that it happened)
    ACCOUNT_DEACTIVATED = "account_deactivated"
    ACCOUNT_REACTIVATED = "account_reactivated"
    CLEARANCE_CHANGED = "clearance_changed"  # old level, new level (a Supervisor or Administrator raises or lowers it)


# ---------------------------------------------------------------- Case Intelligence inside cases (phase CM-5)


class TextSourceKind(StrEnum):
    """What a text index entry was made from. Both are keyed by a SHA-256, so equal content is indexed once."""

    EVIDENCE = "evidence"  # the bytes of an exhibit (evidence_objects.sha256)
    ARTIFACT = "artifact"  # the content of a note, analysis, summary... (artifact_versions.content_sha256)


class TextStatus(StrEnum):
    """The result of reading a file's text, recorded once per content."""

    INDEXED = "indexed"  # text found, split into passages
    NO_TEXT = "no_text"  # readable, but no text (e.g. scanned pages: OCR isn't available yet)
    UNREADABLE = "unreadable"  # damaged, password-protected, or too large to read


# ---------------------------------------------------------------- integrations (phase CM-6)


class ImportItemType(StrEnum):
    """What an outside system adds to a case (docs/case-management/09-integration-contract.md)."""

    LOG_EVENT = "log_event"  # an event found by the Log Analyzer
    ALERT = "alert"  # an alert raised by a monitoring or alerting system
    CDR_RESULT = "cdr_result"  # a result derived from call detail records
    IPDR_RESULT = "ipdr_result"  # a result derived from IP detail records
    OSINT = "osint"  # an item of open-source information, captured lawfully
    INDICATOR = "indicator"  # one or more identifiers on their own (IP, domain, phone, IMEI, IMSI…)
    REPORT = "report"  # a report held in another system (a forensic lab report, for example), by reference


class IndicatorType(StrEnum):
    """Identifiers an imported finding can name. Stored normalised, so the same one matches across cases."""

    IP = "ip"
    DOMAIN = "domain"
    URL = "url"
    EMAIL = "email"
    PHONE = "phone"
    IMEI = "imei"
    IMSI = "imsi"
    ACCOUNT = "account"  # a bank account number or a UPI ID
    FILE_HASH = "file_hash"  # MD5, SHA-1 or SHA-256 of a file


class SourceKind(StrEnum):
    """What kind of system an integration source is."""

    LOG_ANALYZER = "log_analyzer"
    ALERTING = "alerting"
    TELECOM = "telecom"  # CDR and IPDR analysis
    OSINT = "osint"
    THREAT_INTEL = "threat_intel"
    FORENSIC_LAB = "forensic_lab"
    OTHER = "other"


class SourceStatus(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"  # its key stops working at once; what it added stays


class SourceEventType(StrEnum):
    """The permanent history of an integration source."""

    REGISTERED = "registered"
    DISABLED = "disabled"
    ENABLED = "enabled"
    KEY_ROTATED = "key_rotated"


# ---------------------------------------------------------------- reports and governance (phase CM-7)


class ReportType(StrEnum):
    """What a PDF report covers (docs/case-management/03 §5, "Report")."""

    CASE_REPORT = "case_report"  # the case as it stood at one history entry: files, notes, findings
    EVIDENCE_REGISTER = "evidence_register"  # the exhibits only, with hashes, custody and integrity


class ReportCheckResult(StrEnum):
    MATCH = "match"  # the file is exactly the one generated
    MISMATCH = "mismatch"  # the stored copy changed since it was generated
    MISSING = "missing"  # the stored copy is gone
    UNKNOWN = "unknown"  # a submitted file that matches no report


class ReportCheckMethod(StrEnum):
    STORED_COPY = "stored_copy"  # the copy kept in the write-once store, hashed again
    SUBMITTED_COPY = "submitted_copy"  # a copy someone holds (printed, e-mailed), uploaded to be checked


class CheckpointReason(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class RetentionAction(StrEnum):
    """What a retention decision is about. Knight Hawk never deletes a case: see retention.py."""

    RETAIN = "retain"  # keep it, and review again later
    ARCHIVE = "archive"  # read-only archive, inside Knight Hawk
    TRANSFER = "transfer"  # handed over to another body (recorded; the records stay here)
    DISPOSE = "dispose"  # a formal disposal decision: recorded, never carried out by the application


class RetentionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class PolicyStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class JobStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"  # it ran, and found something a person must look at
    FAILED = "failed"  # it could not run, or it found a broken chain
