"""Request and response shapes of the Case Management API (docs/case-management/06-api-contracts.md)."""

import datetime as dt
import uuid
from typing import Any, Literal

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.casemgmt.enums import ArtifactType, CommentTarget, LinkType, Priority
from app.core.enums import Sensitivity
from app.schemas.case_record import DISPLAY_ID_PATTERN
from app.schemas.chat import ChatTurn
from app.schemas.search import SnippetPart
from app.schemas.similar import SIMILAR_RELEVANCE_NOTE, QueryDocumentInfo, SimilarCase


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------- shared pieces


class Person(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    photo: int | None = None  # changes when the person's photo does; None: no photo


class ChatMessageIn(Request):
    """A message to the team (`to` empty or "group") or privately to one member (`to` is that person's id)."""

    to: str | None = Field(None, max_length=40)
    body: str = Field(min_length=1, max_length=4000)


class ChatReadIn(Request):
    thread: str = Field(max_length=40)
    up_to: int = Field(ge=0)


class ChatMessageOut(BaseModel):
    id: int
    sender: Person
    to: Person | None  # None: written to the whole team
    body: str
    at: dt.datetime
    mine: bool


class ChatLast(BaseModel):
    id: int
    sender: Person
    preview: str
    at: dt.datetime


class ChatThread(BaseModel):
    key: str  # "group" or the other person's id
    kind: str  # "group" or "direct"
    title: str
    peer: Person | None
    last: ChatLast | None
    unread: int


class ChatMessages(BaseModel):
    thread: str
    messages: list[ChatMessageOut]


class CaseRef(BaseModel):
    id: uuid.UUID
    display_id: str
    title: str
    case_type: str
    priority: str
    classification: str
    workflow_status: str


class Page(BaseModel):
    total: int
    next_cursor: str | None


# ---------------------------------------------------------------- cases


class OfficialReferenceIn(Request):
    ref_type: str = Field(min_length=1, max_length=32, examples=["FIR"])
    number: str = Field(min_length=1, max_length=64, examples=["0123/2026"])
    issuing_authority: str | None = Field(None, max_length=200)
    ref_date: dt.date | None = None
    source: str = Field("manual", min_length=1, max_length=64)


class OfficialReferenceOut(BaseModel):
    id: uuid.UUID
    ref_type: str
    number: str
    issuing_authority: str | None
    ref_date: dt.date | None
    source: str
    recorded_by: Person | None
    recorded_at: dt.datetime


class ReportedByIn(Request):
    """The person who reported the case. Nothing here is required; `unknown` says no one was there to report it."""

    unknown: bool = False
    name: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    address: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _unknown_has_no_details(self) -> "ReportedByIn":
        if self.unknown and any((self.name, self.phone, self.email, self.address)):
            raise ValueError("The reporter can't be unknown and have details: leave one of them out")
        return self


class ReportedByOut(BaseModel):
    unknown: bool
    name: str | None
    phone: str | None
    email: str | None
    address: str | None


class CaseCreate(Request):
    title: str = Field(min_length=3, max_length=300)
    case_type: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$", examples=["cyber_fraud"])
    description: str = Field(min_length=10, max_length=20_000, description="the plain text of the description: what reports, search and the assistant read")
    description_html: str | None = Field(None, max_length=100_000, description="the same description with the writer's formatting (bold, colours, lists); cleaned by the server")
    priority: Priority = Priority.MEDIUM
    classification: Sensitivity = Sensitivity.RESTRICTED
    jurisdiction: str | None = Field(None, max_length=200)
    lead_investigator_id: uuid.UUID | None = None  # default: the person creating the case
    supervisor_id: uuid.UUID | None = None
    station_id: uuid.UUID | None = None  # the police station that owns the case (default: the organisation's default station)
    official_reference: OfficialReferenceIn | None = None
    reported_by: ReportedByIn | None = Field(None, description="who reported the case, or unknown; optional")


class CaseCreated(BaseModel):
    case_id: uuid.UUID
    display_id: str
    folders: list[str]  # made at once from the case's type
    lead: Person


class CaseSummary(CaseRef):
    case_type_label: str
    official_status: str | None
    created_at: dt.datetime
    official_references: list[str]
    my_role: str | None  # your part on the case's team: lead / sub_investigator / analyst / viewer; none if you see it as a supervisor
    last_activity: dt.datetime | None  # the latest history entry


class CaseList(Page):
    items: list[CaseSummary]


class StatusEventOut(BaseModel):
    field: str
    old_value: str | None
    new_value: str
    reason: str | None
    actor: Person | None
    at: dt.datetime


class FolderOut(BaseModel):
    id: uuid.UUID
    name: str
    system: bool  # made by the application (reports, imports, links) rather than from the case type
    files: int  # files in it that you can see (withdrawn ones are not counted)
    added_at: dt.datetime


class TeamMemberOut(BaseModel):
    user: Person | None
    role: str  # lead / sub_investigator / analyst / viewer
    granted_by: Person | None
    granted_at: dt.datetime
    revoked_by: Person | None
    revoked_at: dt.datetime | None  # set: no longer on the team (what they did stays credited to them)


class PreviousNumberOut(BaseModel):
    old_number: str
    new_number: str
    reason: str
    changed_by: Person | None
    changed_at: dt.datetime


class CaseDetail(CaseSummary):
    description: str
    description_html: str | None = None  # the styled copy, safe to show; None when the description has no formatting
    reported_by: ReportedByOut | None = None  # None: nothing was recorded; unknown=true: no one was there to report it
    jurisdiction: str | None
    supervisor: Person | None
    created_by: Person | None
    lead: Person | None
    references: list[OfficialReferenceOut]
    status_history: list[StatusEventOut]
    folders: list[FolderOut]
    team: list[TeamMemberOut]  # the active team
    previous_numbers: list[PreviousNumberOut] = []  # earlier numbers of the case, oldest first (each one still finds the case)
    can: dict[str, bool]


class CaseNumberChange(Request):
    number: str = Field(min_length=3, max_length=32)
    reason: str = Field(min_length=5, max_length=1000)


class CaseNameChange(Request):
    name: str = Field(min_length=3, max_length=300)
    reason: str = Field(min_length=5, max_length=1000)


class CaseStatusChange(Request):
    field: Literal["workflow", "official"]
    value: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=5, max_length=1000)


class CaseType(BaseModel):
    code: str
    label: str
    folders: list[str]  # made automatically when a case of this type is registered
    evidence_types: list[str]  # suggestions: any short code is accepted


# ---------------------------------------------------------------- files, history and team (docs/case-management/13)


class FolderCreate(Request):
    name: str = Field(min_length=1, max_length=100, examples=["witness-statements"])


class NoteCreate(Request):
    folder: str = Field(min_length=1, max_length=100, examples=["investigation-notes"])
    artifact_type: Literal["note", "analysis", "transcription", "timeline"] = "note"
    title: str = Field(min_length=3, max_length=300)
    content: dict[str, Any] = Field(examples=[{"text": "The complainant shared an OTP during a call (fictional)."}])
    derived_from: list[str] = Field(default_factory=list, max_length=20, examples=[["EV-0001"]],
                                    description="the numbers of the files it is based on (exhibits or other notes)")
    note: str | None = Field(None, max_length=2000)


class NoteRevise(Request):
    content: dict[str, Any]
    expected_version: int = Field(ge=1, description="the version the new text was written from")
    note: str | None = Field(None, max_length=2000)
    derived_from: list[str] = Field(default_factory=list, max_length=20)


class FileOut(BaseModel):
    kind: Literal["note", "evidence"]
    id: uuid.UUID
    display_id: str
    title: str
    folder: str
    status: str  # active / withdrawn
    sealed: bool
    type: str  # the kind of note, or the evidence type
    created_by: Person | None
    created_at: dt.datetime
    updated_at: dt.datetime  # the latest version of a note; the day an exhibit was added
    version_number: int | None  # notes only
    withdrawn_reason: str | None
    withdrawn_at: dt.datetime | None
    withdrawn_by: Person | None = None
    evidence: "EvidenceSummary | None" = None  # exhibits only


class FilesView(BaseModel):
    case: CaseRef
    folders: list[FolderOut]
    files: list[FileOut]  # in the folder asked for, or in every folder


class NoteAdded(BaseModel):
    file: FileOut
    entry: int  # the history entry number


class NoteRevised(BaseModel):
    version: "ArtifactVersionOut"
    entry: int


class EntryOut(BaseModel):
    seq: int
    kind: str
    at: dt.datetime
    actor: Person | None
    summary: str
    subject_type: str | None
    subject_id: str | None
    details: dict[str, Any]


class HistoryView(BaseModel):
    case: CaseRef
    entries: list[EntryOut]  # oldest first
    next_after: int | None  # pass as `after` to get the next page


class HistoryCheck(BaseModel):
    entries: int
    intact: bool
    first_problem: int | None
    problem: str | None


class TeamAdd(Request):
    user_id: uuid.UUID
    role: Literal["sub_investigator", "analyst", "viewer"]  # the lead is changed by handing the case over


class LeadChange(Request):
    user_id: uuid.UUID
    reason: str = Field(min_length=5, max_length=1000)


class MyCase(BaseModel):
    case: CaseRef
    role: str  # lead / sub_investigator / analyst / viewer
    active_from: dt.datetime
    last_activity: dt.datetime | None


class TeamView(BaseModel):
    case: CaseRef
    team: list[TeamMemberOut]  # the active team first, then those who left


# ---------------------------------------------------------------- administration


class RegistryItem(CaseSummary):
    station_code: str
    leads: list[Person]
    supervisor: Person | None
    evidence_count: int
    files: int
    entries: int


class Registry(Page):
    items: list[RegistryItem]


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: dt.datetime
    username: str | None
    action: str
    outcome: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]


class CaseAudit(Page):
    items: list[AuditEntry]


# ---------------------------------------------------------------- evidence (phase CM-2)


class EvidenceUploadForm(Request):
    """An evidence file and its form fields (multipart/form-data). Unknown fields are refused."""

    file: UploadFile
    folder: str = Field(min_length=1, max_length=100, examples=["digital-evidence"])
    title: str = Field(min_length=3, max_length=300)
    evidence_type: str | None = Field(None, max_length=64, examples=["screenshot"])
    description: str | None = Field(None, max_length=5000)
    classification: Sensitivity | None = None  # default: the case's
    source: str | None = Field(None, max_length=300, examples=["complainant's phone (fictional)"])
    collected_at: dt.datetime | None = Field(None, description="with a timezone, e.g. 2026-11-02T14:30:00+05:30")
    collected_by: str | None = Field(None, max_length=200)
    collection_authority: str | None = Field(None, max_length=300, examples=["Seizure memo 12/2026 (fictional)"])
    source_system: str | None = Field(None, max_length=100)
    source_record_id: str | None = Field(None, max_length=200)
    source_hash: str | None = Field(None, max_length=128)


class EvidenceRef(BaseModel):
    id: uuid.UUID
    display_id: str
    title: str


class Custodian(BaseModel):
    user: Person | None
    name: str | None  # a body outside the system


class IntegrityCheckOut(BaseModel):
    result: str  # match / mismatch / missing
    trigger: str
    checked_at: dt.datetime
    checked_by: Person | None
    recorded_sha256: str
    computed_sha256: str | None


class EvidenceSummary(EvidenceRef):
    folder: str
    status: str  # active / withdrawn
    evidence_type: str
    category: str
    classification: str
    sealed: bool
    sha256: str
    size_bytes: int
    mime_type: str
    original_filename: str
    active_content: bool  # programs, scripts, HTML, SVG: never opened by the application
    collected_at: dt.datetime | None
    uploaded_by: Person | None
    uploaded_at: dt.datetime
    custodian: Custodian | None
    last_check: IntegrityCheckOut | None


class EvidenceAdded(BaseModel):
    evidence: EvidenceSummary
    entry: int  # the history entry number
    duplicates: list[EvidenceRef]  # exhibits of the case with exactly the same bytes


class SourceReferenceOut(BaseModel):
    source_system: str
    source_record_id: str | None
    source_hash: str | None
    original_reference: str | None
    imported_by: Person | None
    imported_at: dt.datetime


class EvidenceVersionOut(BaseModel):
    id: uuid.UUID
    version_number: int
    original_filename: str
    display_filename: str
    mime_type: str
    declared_mime_type: str | None
    size_bytes: int
    sha256: str
    uploaded_by: Person | None
    uploaded_at: dt.datetime


class CustodyEventOut(BaseModel):
    id: int
    event_type: str
    actor: Person | None
    from_custodian: Custodian | None
    to_custodian: Custodian | None
    occurred_at: dt.datetime
    occurred_tz: str | None
    recorded_at: dt.datetime
    reason: str | None
    method: str | None
    verification_sha256: str | None
    related_event_id: int | None
    authorization_ref: str | None
    details: dict[str, Any]


class EvidenceDetail(EvidenceSummary):
    case: CaseRef
    description: str | None
    source: str | None
    collected_tz: str | None
    collected_by: str | None
    collection_authority: str | None
    created_by: Person | None
    version: EvidenceVersionOut
    sources: list[SourceReferenceOut]
    sealed_reason: str | None
    sealed_by: Person | None
    sealed_at: dt.datetime | None
    withdrawn_reason: str | None
    withdrawn_at: dt.datetime | None
    pending_transfer: CustodyEventOut | None
    can: dict[str, bool]


class DerivedVersionOut(BaseModel):
    artifact_id: uuid.UUID
    display_id: str
    title: str
    artifact_type: str
    version_id: uuid.UUID
    version_number: int
    author: Person | None
    created_at: dt.datetime
    change_note: str | None


class EvidenceVersions(BaseModel):
    original: EvidenceVersionOut  # the only version an exhibit ever has
    derived: list[DerivedVersionOut]  # analyses, transcriptions and notes based on it


class CustodyView(BaseModel):
    evidence: EvidenceRef
    current_custodian: Custodian | None
    pending_transfer: CustodyEventOut | None
    events: list[CustodyEventOut]  # oldest first


class CustodyAction(Request):
    action: Literal["transfer", "acknowledge", "decline"]
    to_user_id: uuid.UUID | None = None  # transfer to an officer (pending until they acknowledge)
    to_external: str | None = Field(None, max_length=200, examples=["State Forensic Science Laboratory (fictional)"])
    receipt_reference: str | None = Field(None, max_length=200)  # required for a transfer to an outside body
    reason: str | None = Field(None, max_length=1000)
    method: str | None = Field(None, max_length=100, examples=["sealed envelope, hand delivery"])
    authorization_ref: str | None = Field(None, max_length=200)
    transfer_event_id: int | None = None  # for acknowledge / decline
    occurred_at: dt.datetime | None = None  # default: now


class VerificationOut(IntegrityCheckOut):
    evidence: EvidenceRef


class DownloadLink(BaseModel):
    url: str  # works once, without the login header, until expires_at
    expires_at: dt.datetime


class PreviewPage(BaseModel):
    number: int | None
    text: str


class Preview(BaseModel):
    evidence: EvidenceRef
    kind: Literal["text", "none"]
    pages: list[PreviewPage]
    truncated: bool
    reason: str | None  # why there is no preview


class SealChange(Request):
    reason: str = Field(min_length=5, max_length=1000)


class IntegrityItem(BaseModel):
    evidence: EvidenceRef
    case: CaseRef
    sha256: str
    size_bytes: int
    sealed: bool
    last_check: IntegrityCheckOut | None


class IntegrityReport(Page):
    counts: dict[str, int]  # match / mismatch / missing / never_checked
    items: list[IntegrityItem]  # failures first, then never checked, then the oldest checks


# ---------------------------------------------------------------- tasks, comments, notes and notifications


class OptionalReason(Request):
    reason: str | None = Field(None, max_length=1000)


class RequiredReason(Request):
    reason: str = Field(min_length=5, max_length=1000)


class AccessEventOut(BaseModel):
    id: int
    user: Person | None
    change: str  # membership_granted / membership_revoked
    old_value: str | None
    new_value: str | None
    actor: Person | None
    reason: str | None
    at: dt.datetime


class TaskCreate(Request):
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(None, max_length=10_000)
    assignee_id: uuid.UUID | None = None
    due_at: dt.datetime | None = None


class TaskStatusChange(Request):
    status: Literal["open", "in_progress", "done", "cancelled"]
    reason: str | None = Field(None, max_length=1000)  # required to cancel or reopen
    expected_version: int | None = None


class TaskAssign(Request):
    assignee_id: uuid.UUID | None = None  # none: unassigned
    reason: str | None = Field(None, max_length=1000)
    expected_version: int | None = None


class TaskRef(BaseModel):
    id: uuid.UUID
    display_id: str
    title: str
    status: str


class TaskOut(TaskRef):
    case: CaseRef
    description: str | None
    assignee: Person | None
    due_at: dt.datetime | None
    created_by: Person | None
    created_at: dt.datetime
    version: int


class TaskEventOut(BaseModel):
    field: str
    old_value: str | None
    new_value: str | None
    actor: Person | None
    reason: str | None
    at: dt.datetime


class TaskDetail(TaskOut):
    events: list[TaskEventOut]
    can: dict[str, bool]


class CommentCreate(Request):
    target_type: CommentTarget
    target_id: str = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1, max_length=10_000)
    replaces_comment_id: uuid.UUID | None = None  # an edit is a new comment replacing the old one


class CommentOut(BaseModel):
    id: uuid.UUID
    target_type: str
    target_id: str
    author: Person | None
    body: str
    created_at: dt.datetime
    replaces_comment_id: uuid.UUID | None
    replaced_by: uuid.UUID | None
    current: bool  # not replaced by a newer version


class ArtifactVersionOut(BaseModel):
    id: uuid.UUID
    version_number: int
    content: dict[str, Any]
    content_sha256: str
    derived_from: list[str]  # version IDs it is based on
    author: Person | None
    created_at: dt.datetime
    change_note: str | None


class ArtifactHistory(BaseModel):
    id: uuid.UUID
    display_id: str
    title: str
    artifact_type: str
    folder: str
    status: str  # active / withdrawn
    withdrawn_reason: str | None
    case: CaseRef
    sealed: bool
    sealed_reason: str | None
    sealed_by: Person | None
    sealed_at: dt.datetime | None
    versions: list[ArtifactVersionOut]  # oldest first
    can: dict[str, bool]


class NotificationOut(BaseModel):
    id: int
    kind: str
    payload: dict[str, Any]
    created_at: dt.datetime
    read_at: dt.datetime | None


class NotificationList(Page):
    unread: int
    items: list[NotificationOut]


class Marked(BaseModel):
    marked: int


# ---------------------------------------------------------------- CM-4: choosing colleagues, dashboards, case links, report preview


class StationOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    district: str | None
    status: str


class Colleague(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    org_role: str
    roles: list[str] = []  # for the team of a case: the parts this person can be given


class CaseCount(BaseModel):
    code: str
    label: str
    count: int


class CasesOverview(BaseModel):
    total: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    by_type: list[CaseCount]


class DayCount(BaseModel):
    day: dt.date
    entries: int


class ActivityOverview(BaseModel):
    total: int  # history entries in all
    per_day: list[DayCount]  # the last 30 days (UTC), oldest first


class FilesOverview(BaseModel):
    notes: int
    exhibits: int
    withdrawn: int


class IntegrityAlert(BaseModel):
    evidence_id: uuid.UUID
    display_id: str
    title: str
    case_id: uuid.UUID
    case_display_id: str
    result: str
    checked_at: dt.datetime


class EvidenceOverview(BaseModel):
    items: int
    bytes: int
    integrity: dict[str, int]  # result of each exhibit's latest check: match / mismatch / missing / never_checked
    alerts: list[IntegrityAlert]


class TasksOverview(BaseModel):
    open: int
    overdue: int


class EntryWithCase(EntryOut):
    case: CaseRef


class AdminOverview(BaseModel):
    cases: CasesOverview
    files: FilesOverview
    activity: ActivityOverview
    evidence: EvidenceOverview
    tasks: TasksOverview
    recent_entries: list[EntryWithCase]
    generated_at: dt.datetime


class ContributionTotals(BaseModel):
    entries: int
    notes: int
    revisions: int
    evidence: int


class MyContributions(BaseModel):
    entries: list[EntryWithCase]
    totals: ContributionTotals
    # Your work in cases you can no longer open (an access that ended): still credited to you; numbers only.
    no_longer_open: ContributionTotals


class LinkCreate(Request):
    """Link another investigation (target_case_id) or, since CM-5, a past case of the knowledge base (knowledge_case)."""

    target_case_id: uuid.UUID | None = None
    knowledge_case: str | None = Field(None, pattern=DISPLAY_ID_PATTERN, description="A knowledge-base case's ID (Similar Cases)")
    link_type: LinkType
    reason: str = Field(min_length=10, max_length=1000, examples=["Fictional: the same mule account receives money in both cases."])

    @model_validator(mode="after")
    def _one_target(self) -> "LinkCreate":
        if (self.target_case_id is None) == (self.knowledge_case is None):
            raise ValueError("Give either target_case_id (another investigation) or knowledge_case (a past case), not both")
        return self


class LinkTypeOut(BaseModel):
    code: str
    label: str


class LinkTarget(BaseModel):
    """The linked case as recorded when the link was made."""

    case_id: str | None = None
    display_id: str | None = None
    title: str | None = None
    case_type: str | None = None


class KnowledgeCaseRef(BaseModel):
    """A past case of the knowledge base, as recorded when the link was made (CM-5)."""

    case_id: str | None = None
    display_id: str
    title: str | None = None
    court: str | None = None
    decision_date: str | None = None
    source_system: str | None = None


class OutgoingLink(BaseModel):
    link_id: uuid.UUID
    artifact_id: uuid.UUID
    display_id: str
    status: str  # active, or withdrawn (still shown: history is kept)
    withdrawn_reason: str | None
    link_type: str | None
    label: str
    reason: str | None
    target: LinkTarget
    target_now: CaseRef | None  # the linked case today, if the viewer can open it
    knowledge_case: KnowledgeCaseRef | None = None  # a link to a past case instead
    knowledge_visible: bool = False  # the viewer may open that past case in Case Intelligence
    created_by: Person | None
    created_at: dt.datetime


class IncomingLink(BaseModel):
    case: CaseRef
    link_type: str
    label: str
    reason: str
    created_by: Person | None
    created_at: dt.datetime


class CaseLinks(BaseModel):
    case: CaseRef
    outgoing: list[OutgoingLink]
    incoming: list[IncomingLink]
    link_types: list[LinkTypeOut]


class LinkAdded(BaseModel):
    link_id: uuid.UUID
    artifact_id: uuid.UUID
    display_id: str
    entry: int  # the history entry number


class ReportCase(CaseRef):
    description: str
    jurisdiction: str | None
    official_status: str | None
    references: list[str]


class ReportEvidence(BaseModel):
    display_id: str
    title: str
    folder: str
    status: str
    withdrawn_reason: str | None
    evidence_type: str
    category: str
    classification: str
    sealed: bool
    sha256: str
    size_bytes: int
    mime_type: str
    original_filename: str | None
    collected_at: dt.datetime | None
    collected_by: str | None
    collection_authority: str | None
    source: str | None
    uploaded_by: Person | None
    uploaded_at: dt.datetime | None
    custodian: Custodian | None
    transfer_pending: bool
    last_check: IntegrityCheckOut | None


class ReportArtifact(BaseModel):
    display_id: str
    title: str
    artifact_type: str
    folder: str
    status: str
    withdrawn_reason: str | None
    version_number: int
    version_created_at: dt.datetime
    author: Person | None
    change_note: str | None


class ReportIntegrity(BaseModel):
    match: int
    mismatch: int
    missing: int
    never_checked: int


class ReportImport(BaseModel):
    """A finding imported from an outside system, with its provenance."""

    status: str
    display_id: str | None
    title: str | None
    item_type: str | None
    source: str | None
    source_record_id: str | None
    source_hash: str | None
    authority_ref: str | None
    observed_at: str | None
    imported_by: Person | None
    imported_at: dt.datetime | None
    version_number: int | None
    fictional: bool


class ReportHistory(BaseModel):
    entries: int
    intact: bool


class ReportPreview(BaseModel):
    case: ReportCase
    folders: list[str]
    history: ReportHistory
    evidence: list[ReportEvidence]
    artifacts: list[ReportArtifact]
    imports: list[ReportImport] = []
    integrity: ReportIntegrity
    team: list[TeamMemberOut]
    withheld_entries: int  # files the viewer may not see (sealed), left out
    generated_at: dt.datetime
    generated_by: Person | None
    disclaimer: str
    preview_note: str


# ---------------------------------------------------------------- Case Intelligence inside cases (phase CM-5)


class CISource(BaseModel):
    """An exhibit or a note of the case, as Case Intelligence cites it."""

    path: str
    kind: Literal["evidence", "artifact"]
    item_id: uuid.UUID  # the exhibit's or the artifact's ID
    version_id: uuid.UUID
    display_id: str
    title: str
    version_number: int
    mime_type: str | None
    evidence_type: str | None
    artifact_type: str | None


class NotRead(BaseModel):
    display_id: str
    reason: str


class Coverage(BaseModel):
    """What of the case Case Intelligence could read. Nothing missing is ever guessed."""

    documents: int  # exhibits you may see
    readable: int  # of which the text can be read (PDF, Word, text files)
    indexed: int  # read, with text
    pending: list[str]  # readable, not read yet (exhibit IDs)
    no_text: list[str]  # read, but no text found (e.g. scanned pages: no text recognition yet)
    unreadable: list[NotRead]  # damaged, password-protected, or failed its integrity check
    not_readable: list[NotRead]  # images, audio, video, programs: no text to read
    notes: int  # notes, analyses, summaries, links
    notes_indexed: int
    passages: int
    passages_without_meaning: int  # found by words only until their meaning vector exists
    embedding_model: str | None
    complete: bool


class IntelligenceStatus(BaseModel):
    coverage: Coverage


class PrepareRequest(Request):
    """Nothing to say: reading what the case's files still lack."""


class CaseSearchRequest(Request):
    query: str = Field(min_length=1, max_length=500, examples=["98450 00000 (fictional)"])
    mode: Literal["hybrid", "keyword", "semantic"] = "hybrid"
    limit: int = Field(20, ge=1, le=50)


class CaseSearchPassage(BaseModel):
    chunk_id: int
    page_start: int | None
    page_end: int | None
    snippet: list[SnippetPart]  # plain-text parts; match=True marks the search words
    matched_by: list[str]  # "keyword", "semantic"
    similarity: float | None


class CaseSearchResult(BaseModel):
    source: CISource
    also_in: list[CISource]  # the same file is also these exhibits
    matching_passages: int
    passages: list[CaseSearchPassage]


class CaseSearchResponse(BaseModel):
    query: str
    mode: str
    total_sources: int
    total_passages: int
    results: list[CaseSearchResult]
    notices: list[str]
    coverage: Coverage


class InvestigationPassage(BaseModel):
    source: str | None  # "EV-0002 v1, p.3"
    page_start: int | None
    page_end: int | None
    text: str


class InvestigationPair(BaseModel):
    similarity: float
    this_case: InvestigationPassage
    other_case: InvestigationPassage


class SharedFile(BaseModel):
    sha256: str
    here: list[str]  # exhibit IDs in this case
    there: list[str]  # exhibit IDs in the other case


class SimilarInvestigation(BaseModel):
    case: CaseRef
    relevance: int = Field(ge=0, le=100)
    match_type: list[str]  # "text", "provisions", "same_file"
    text_similarity: float | None
    matched_passages: int
    shared_provisions: list[str]
    shared_files: list[SharedFile]
    passage_pairs: list[InvestigationPair]
    reasons: list[str]
    differences: list[str]
    linked: bool  # this case already links to it


class KnowledgeMatch(SimilarCase):
    linked: bool  # this case already links to it


class CaseSimilarResponse(BaseModel):
    query: QueryDocumentInfo
    investigations: list[SimilarInvestigation]
    investigations_total: int
    knowledge_base: list[KnowledgeMatch]
    knowledge_total: int
    notices: list[str]
    coverage: Coverage
    method_note: str
    relevance_note: str = SIMILAR_RELEVANCE_NOTE


class AskRequest(Request):
    """The conversation is kept by the browser and sent back each time; nothing is stored on the server."""

    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)


class AnswerSource(BaseModel):
    id: str  # "S1", "S2"... as cited in the answer
    kind: Literal["case_record", "evidence", "artifact"]
    display_id: str  # the case, the exhibit or the note
    title: str
    path: str | None
    version_number: int | None
    page_start: int | None
    page_end: int | None
    excerpt: str
    item_id: str | None  # the exhibit's or the artifact's ID
    cited: bool


class CaseAnswer(BaseModel):
    answer: str
    answered: bool  # False when the records don't contain the answer
    sources: list[AnswerSource]
    notices: list[str]
    model: str
    seconds: float
    disclaimer: str
    coverage: Coverage


class OffenceCitation(BaseModel):
    display_id: str
    title: str
    kind: str
    item_id: str
    path: str
    pages: list[int]


class OffenceCited(BaseModel):
    key: str
    label: str  # "Section 318 of the BNS"
    act: str
    category: Literal["criminal_law", "procedure_and_evidence", "constitution", "other_law"]
    description: str | None  # the common heading of a well-known section, for orientation
    mentions: int
    cited_in: list[OffenceCitation]


class PastCaseRef(BaseModel):
    display_id: str
    title: str | None
    relevance: int


class OffenceSuggestion(BaseModel):
    key: str
    label: str
    act: str
    category: str
    description: str | None
    count: int  # how many of the similar past cases cite it
    cases: list[PastCaseRef]


class OffenceSuggestions(BaseModel):
    cited_here: list[OffenceCited]
    from_similar_cases: list[OffenceSuggestion]
    similar_cases_considered: int
    notices: list[str]
    disclaimer: str
    coverage: Coverage


class TimelineRebuild(Request):
    message: str | None = Field(None, max_length=2000)


class TimelineSourceRef(BaseModel):
    kind: str  # "evidence", "artifact" or "record"
    display_id: str
    title: str | None
    path: str | None
    version_number: int | None
    version_id: str | None
    item_id: str | None


class TimelineEvent(BaseModel):
    date: str  # ISO date
    date_text: str | None  # as written in the source
    description: str  # the sentence around the date, or what the record says
    kind: str  # dated_mention, order_under_appeal, evidence_collected, official_reference
    method: Literal["text", "record"]
    page: int | None
    source: TimelineSourceRef


class TimelineUsed(TimelineSourceRef):
    events: int


class Timeline(BaseModel):
    folder: str
    artifact_id: uuid.UUID
    display_id: str
    version_number: int
    versions: int
    created_at: dt.datetime
    author: Person | None
    based_on_entry: int | None
    method: str | None
    shared_view: str | None
    events: list[TimelineEvent]
    sources_used: list[TimelineUsed]
    not_used: list[NotRead]


class TimelineView(BaseModel):
    timeline: Timeline | None  # none built yet, or you may not see it


class TimelineRebuilt(BaseModel):
    entry: int  # the history entry number
    artifact_id: uuid.UUID
    display_id: str
    version_number: int
    events: int
    sources: int
    not_used: list[NotRead]


# ---------------------------------------------------------------- integrations (phase CM-6, docs/case-management/09)


class IdentifierIn(BaseModel):
    type: str = Field(max_length=16, description="ip, domain, url, email, phone, imei, imsi, account or file_hash")
    value: str = Field(max_length=600)


class AddToCase(Request):
    """One finding from an outside system, added to a case the person may add to (the integration contract)."""

    case_id: uuid.UUID
    item_type: str = Field(max_length=16, description="log_event, alert, cdr_result, ipdr_result, osint, indicator or report")
    source_record_id: str = Field(max_length=200, description="The record's ID in the source system")
    source_hash: str = Field(max_length=140, description="SHA-256 of the record as the source computed it: 'sha256:<hex>'")
    summary: str = Field(max_length=2000, description="What was found, in a few sentences")
    title: str | None = Field(default=None, max_length=300)
    payload_ref: str | None = Field(default=None, max_length=500, description="Where the full record stays, in the source system")
    authority_ref: str | None = Field(default=None, max_length=300, description="The legal authorisation it was obtained under")
    observed_at: dt.datetime | None = Field(default=None, description="When it happened, with its timezone")
    observed_until: dt.datetime | None = None
    identifiers: list[IdentifierIn] = Field(default_factory=list, max_length=100)
    details: dict[str, Any] = Field(default_factory=dict, description="The derived result: at most 64,000 bytes")
    message: str | None = Field(default=None, max_length=2000, description="The history entry's wording (a default one is written)")


class SourceRefOut(BaseModel):
    id: uuid.UUID | None
    code: str | None = None
    name: str | None = None
    kind: str | None = None
    kind_label: str | None = None
    fictional: bool = False
    status: str | None = None


class IdentifierOut(BaseModel):
    type: str
    label: str
    value: str


class ImportItem(BaseModel):
    artifact_id: uuid.UUID
    display_id: str  # IMP-0001
    status: str  # active, or withdrawn (still shown: history is kept)
    withdrawn_reason: str | None
    title: str
    version_number: int
    versions: int
    item_type: str | None
    item_type_label: str
    summary: str | None
    source: SourceRefOut
    source_record_id: str | None
    source_hash: str | None
    payload_ref: str | None
    authority_ref: str | None
    observed_at: str | None  # as the source gave it, with its timezone
    observed_until: str | None
    identifiers: list[IdentifierOut]
    imported_by: Person | None
    imported_at: dt.datetime
    received_with: str | None  # the first characters of the source key that sent it
    content_sha256: str
    fictional: bool


class ItemTypeInfo(BaseModel):
    code: str
    label: str
    description: str
    observed_at_required: bool
    authority_by_default: bool


class IdentifierTypeInfo(BaseModel):
    code: str
    label: str
    format: str


class IntegrationContract(BaseModel):
    version: str
    item_types: list[ItemTypeInfo]
    identifier_types: list[IdentifierTypeInfo]
    limits: dict[str, int]
    headers: dict[str, str]


class ImportsView(BaseModel):
    case: CaseRef
    imports: list[ImportItem]
    by_type: dict[str, int]
    item_types: list[ItemTypeInfo]


class ImportAdded(BaseModel):
    entry: int  # the history entry number
    finding: ImportItem
    updated: bool  # a new version of a record imported before: its source changed it


class OtherCaseImport(BaseModel):
    display_id: str
    title: str
    item_type: str
    item_type_label: str
    source: str | None
    imported_at: dt.datetime


class OtherCase(BaseModel):
    case: CaseRef
    imports: list[OtherCaseImport]
    linked: bool  # this case already links to it


class IdentifierDetail(IdentifierOut):
    as_received: str | None
    in_this_case: list[str]  # other findings of this case naming it
    other_cases: list[OtherCase]


class ImportVersion(BaseModel):
    version_number: int
    source_hash: str | None
    change_note: str | None
    imported_by: Person | None
    imported_at: dt.datetime
    received_with: str | None
    content_sha256: str
    current: bool


class ImportUsedBy(BaseModel):
    artifact_id: uuid.UUID
    display_id: str
    title: str
    artifact_type: str
    version_number: int


class ImportDetail(ImportItem):
    identifiers: list[IdentifierDetail]
    case: CaseRef
    details: dict[str, Any]
    history: list[ImportVersion]
    used_by: list[ImportUsedBy]
    policy_note: str


class IndicatorImport(BaseModel):
    artifact_id: uuid.UUID
    display_id: str
    status: str
    item_type_label: str


class IndicatorRow(BaseModel):
    type: str
    label: str
    value: str
    imports: list[IndicatorImport]
    other_cases: list[OtherCase]


class IndicatorTotals(BaseModel):
    identifiers: int
    with_matches: int
    cases: int


class IndicatorsView(BaseModel):
    case: CaseRef
    indicators: list[IndicatorRow]
    totals: IndicatorTotals
    note: str


class SourcePolicy(BaseModel):
    allowed_item_types: list[str]
    authority_required_for: list[str]
    min_case_classification: str
    legal_basis: str | None


class SourceEventOut(BaseModel):
    event_type: str
    by: Person | None
    reason: str | None
    key_prefix: str | None
    at: dt.datetime


class IntegrationSourceOut(SourceRefOut):
    id: uuid.UUID
    description: str | None
    policy: SourcePolicy
    key_prefix: str
    key_issued_at: dt.datetime
    created_by: Person | None
    created_at: dt.datetime
    imports: int
    cases: int
    last_import_at: dt.datetime | None
    history: list[SourceEventOut]


class SourceCreate(Request):
    code: str = Field(max_length=63)
    name: str = Field(max_length=200)
    kind: str = Field(max_length=32)
    legal_basis: str = Field(max_length=2000, description="Under what authority the source's data is obtained")
    allowed_item_types: list[str] = Field(max_length=10)
    authority_required_for: list[str] | None = Field(default=None, max_length=10)
    min_case_classification: Sensitivity = Sensitivity.INTERNAL
    description: str | None = Field(default=None, max_length=2000)


class SourceKeyIssued(BaseModel):
    source: IntegrationSourceOut
    key: str  # shown this once: only its SHA-256 is stored
    key_note: str


class SourceStatusChange(Request):
    enabled: bool
    reason: str = Field(max_length=1000)


class SourceKeyRotation(Request):
    reason: str = Field(max_length=1000)


class TestFinding(BaseModel):
    id: str
    system: str
    item_type: str
    item_type_label: str
    source_record_id: str
    title: str
    summary: str
    payload_ref: str | None
    authority_ref: str | None
    observed_at: str | None
    observed_until: str | None
    identifiers: list[IdentifierIn]
    details: dict[str, Any]
    source_hash: str
    updates: str | None = None  # the finding this one is a later version of (the source changed its record)


class TestSourceView(BaseModel):
    registered: bool
    source: SourceRefOut | None
    findings: list[TestFinding]
    note: str


class TestSourceSend(Request):
    finding_id: str = Field(max_length=64)
    case_id: uuid.UUID
    message: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------- reports and governance (phase CM-7)


class ReportCreate(Request):
    """Generate a signed PDF report of the case as it stands, as a new report version added to the case."""

    report_type: Literal["case_report", "evidence_register"] = "case_report"
    purpose: str = Field(max_length=500, description="What the report is for: printed in it")


class ReportCheckView(BaseModel):
    result: str  # match, mismatch, missing, unknown
    method: str  # stored_copy, submitted_copy
    computed_sha256: str | None
    checked_at: dt.datetime
    checked_by: Person | None


class ReportVersion(BaseModel):
    id: uuid.UUID  # the export's ID: download links and checks use it
    display_id: str  # RPT-0001
    version_number: int
    report_type: str
    title: str
    purpose: str
    file_name: str | None
    sha256: str
    size_bytes: int
    page_count: int
    as_of_entry: int  # the report describes the case as it stood at this history entry
    case_id: uuid.UUID
    withheld_entries: int
    generated_by: Person | None
    generated_at: dt.datetime
    sealed: bool
    last_check: ReportCheckView | None


class ReportTypeInfo(BaseModel):
    code: str
    label: str


class ReportsView(BaseModel):
    case: CaseRef
    entries: int  # the case's history entries now
    reports: list[ReportVersion]
    report_types: list[ReportTypeInfo]


class ReportGenerated(BaseModel):
    entry: int  # the history entry number
    report: ReportVersion


class ReportEvent(BaseModel):
    kind: str  # check, download
    at: dt.datetime
    by: Person | None
    result: str | None
    method: str | None


class ReportDetail(ReportVersion):
    history: list[ReportEvent]


class ReportCheck(BaseModel):
    result: str  # match: exactly the file generated; mismatch / missing: the stored copy; unknown: no such report
    method: str
    computed_sha256: str | None
    recorded_sha256: str | None  # only when you may see the report
    checked_at: dt.datetime
    report: ReportVersion | None  # only when you may see it
    message: str


class LegalHoldCreate(Request):
    reason: str = Field(max_length=2000)
    authority_ref: str | None = Field(default=None, max_length=300, description="The order or instruction the hold follows")


class RequiredNote(Request):
    reason: str = Field(max_length=2000)


class LegalHoldOut(BaseModel):
    id: uuid.UUID
    reason: str
    authority_ref: str | None
    placed_by: Person | None
    placed_at: dt.datetime
    released_by: Person | None
    released_at: dt.datetime | None
    release_reason: str | None
    active: bool


class LegalHoldWithCase(LegalHoldOut):
    case: CaseRef


class RetentionPolicyCreate(Request):
    code: str = Field(max_length=63)
    name: str = Field(max_length=200)
    review_after_years: int = Field(ge=1, le=100)
    legal_basis: str = Field(max_length=2000, description="The rule or schedule the policy follows")
    case_types: list[str] = Field(default_factory=list, max_length=50, description="Empty: every type of case")
    description: str | None = Field(default=None, max_length=2000)


class RetentionPolicyOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    review_after_years: int
    case_types: list[str]
    legal_basis: str
    status: str
    created_by: Person | None
    created_at: dt.datetime


class PolicyRef(BaseModel):
    id: uuid.UUID
    name: str


class RetentionDecisionCreate(Request):
    action: Literal["retain", "archive", "transfer", "dispose"]
    reason: str = Field(max_length=2000)
    policy_id: uuid.UUID | None = None
    review_on: dt.date | None = Field(default=None, description="For 'retain': when to review again")
    transfer_to: str | None = Field(default=None, max_length=300, description="For 'transfer': to whom")


class RetentionDecide(Request):
    approve: bool
    note: str = Field(max_length=2000)


class RetentionDecisionOut(BaseModel):
    id: uuid.UUID
    action: str
    action_label: str
    reason: str
    review_on: dt.date | None
    transfer_to: str | None
    policy: PolicyRef | None
    proposed_by: Person | None
    proposed_at: dt.datetime
    status: str
    decided_by: Person | None
    decided_at: dt.datetime | None
    decision_note: str | None
    outside_action: bool  # an approved disposal: for the organisation's formal process, outside Knight Hawk


class RetentionDecisionWithCase(RetentionDecisionOut):
    case: CaseRef


class RetentionActionInfo(BaseModel):
    code: str
    label: str


class CaseGovernance(BaseModel):
    holds: list[LegalHoldOut]
    on_hold: bool
    decisions: list[RetentionDecisionOut]
    policy: RetentionPolicyOut | None
    closed_at: dt.datetime | None
    review_due_on: dt.date | None
    review_due: bool
    can_decide: bool
    actions: list[RetentionActionInfo]


class DueForReview(BaseModel):
    case: CaseRef
    policy: PolicyRef
    closed_at: dt.datetime | None
    due_on: dt.date
    on_hold: bool


class RetentionOverview(BaseModel):
    policies: list[RetentionPolicyOut]
    due: list[DueForReview]
    waiting: list[RetentionDecisionWithCase]
    actions: list[RetentionActionInfo]


class JobRunOut(BaseModel):
    id: int
    job: str
    label: str
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime
    summary: dict[str, Any]
    started_by: Person | None


class JobOverview(BaseModel):
    job: str
    label: str
    every_hours: int
    last_run: JobRunOut | None
    next_due: dt.datetime | None


class CheckpointOut(BaseModel):
    id: int
    chain_seq: int
    chain_hash: str
    key_id: str
    reason: str
    stored_sha256: str
    created_at: dt.datetime
    created_by: Person | None


class ChainState(BaseModel):
    events: int  # Case Management events in the chain
    last_seq: int | None
    last_hash: str | None
    since_last_checkpoint: int
    key_id: str  # the key that signs checkpoints now (a fingerprint, not the key)


class GovernanceSettings(BaseModel):
    mfa_required: bool
    checkpoint_key_set: bool  # False: derived from AUDIT_SECRET (set CM_CHECKPOINT_KEY, kept apart from the database)
    mfa_key_set: bool
    runtime_login: bool  # the application connects as its own login (no DELETE on case records)
    test_source: bool


class GovernanceOverview(BaseModel):
    chain: ChainState
    checkpoints: list[CheckpointOut]
    jobs: list[JobOverview]
    legal_holds: list[LegalHoldWithCase]
    settings: GovernanceSettings


for _model in (FileOut, FilesView, NoteAdded, NoteRevised):
    _model.model_rebuild()  # they name classes defined further down
