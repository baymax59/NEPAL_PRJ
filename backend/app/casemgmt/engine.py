"""The case engine: cases, folders, notes and their versions, withdrawing files, statuses (docs/case-management/13-plain-case-design.md).

Every change is a new row and a history entry (history.py). Nothing is overwritten or removed: a wrong note is revised (a new version),
a wrong file is withdrawn with a reason. The only things that move are statuses (case_status_events) and the seal / withdrawn fields
of a file. Callers check access first (access.py) and write the audit events; each public function runs inside the caller's transaction
and takes the case's lock, so the changes of one case take turns.
"""

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.access import sensitivities_up_to
from app.auth.mfa import require_strong_auth
from app.casemgmt import hashing, history, rich_text
from app.casemgmt.access import (
    CASE_CREATORS,
    LEAD_CAPABLE,
    SUPERVISING,
    hidden_file_ids,
    is_case_lead,
    require,
    rights,
    supervises,
    works_at,
)
from app.casemgmt.case_types import case_type
from app.casemgmt.enums import (
    ArtifactType,
    AuthorizationChange,
    FileStatus,
    HistoryKind,
    MemberRole,
    OrgRole,
    StatusField,
    WorkflowStatus,
)
from app.casemgmt.errors import Conflict, Forbidden, Invalid, NotVisible
from app.casemgmt.models import (
    Artifact,
    ArtifactVersion,
    AuthorizationEvent,
    CaseFamily,
    CaseFolder,
    CaseMember,
    CaseNumberChange,
    CaseOfficialReference,
    CaseStatusEvent,
    EvidenceItem,
    EvidenceVersion,
    Organization,
)
from app.casemgmt.notifications import notify
from app.casemgmt.stations import station_for_new_case
from app.db.models import User

# Folder names: letters, digits, spaces and "._-" (e.g. "digital-evidence"), at most 100 characters.
FOLDER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$")
MAX_CONTENT_BYTES = 200_000  # one note or analysis; files are evidence
MAX_DERIVED_FROM = 20
INFORMATION_FOLDER = "case-information"
ARTIFACT_PREFIX = {
    ArtifactType.CASE_SUMMARY: "SUM", ArtifactType.OFFICIAL_REFERENCES: "REF", ArtifactType.NOTE: "NOTE",
    ArtifactType.ANALYSIS: "ANL", ArtifactType.TRANSCRIPTION: "TRN", ArtifactType.TIMELINE: "TML",
    ArtifactType.REPORT: "RPT", ArtifactType.IMPORT: "IMP", ArtifactType.LINK: "LNK",
}
# What people add by hand. Summaries and references come with the case; reports, imports and links are produced by their own
# features, each with its own checks.
ADDABLE_TYPES = {ArtifactType.NOTE, ArtifactType.ANALYSIS, ArtifactType.TRANSCRIPTION, ArtifactType.TIMELINE}
# Kept exactly as they were made: they are never revised, and the first two are the registration record (never withdrawn).
KEPT_AS_MADE = {ArtifactType.LINK: "a link to another case, which can't be edited: withdraw it and link again",
                ArtifactType.IMPORT: "received from an outside system and kept exactly as received: add a note that refers to it, or withdraw it",
                ArtifactType.REPORT: "a generated report, kept exactly as it was signed: generate a new version instead",
                ArtifactType.CASE_SUMMARY: "the case summary written at registration, which doesn't change",
                ArtifactType.OFFICIAL_REFERENCES: "the official references recorded at registration: add a reference instead"}
NEVER_WITHDRAWN = {ArtifactType.CASE_SUMMARY, ArtifactType.OFFICIAL_REFERENCES}


@dataclass
class CreatedCase:
    family: CaseFamily
    folders: list[CaseFolder]
    lead: User


# ---------------------------------------------------------------- small building blocks


def _lock_family(session: Session, family_id, *reload) -> CaseFamily:
    """Write operations on one case take turns (numbering of files and history entries stays gap-free and unique).

    Objects passed in `reload` are re-read once the lock is held, so decisions use the latest statuses.
    """
    family = session.scalar(select(CaseFamily).where(CaseFamily.id == family_id).with_for_update())
    if family is None:
        raise NotVisible()
    for item in reload:
        session.refresh(item)
    return family


def _reason(reason: str | None) -> str:
    reason = (reason or "").strip()
    if not 5 <= len(reason) <= 1000:
        raise Invalid("Give a reason (5 to 1,000 characters): it is kept with the change")
    return reason


def _allowed(current: str, target: str, table: dict, what: str) -> None:
    allowed = {str(t.value if hasattr(t, "value") else t) for t in table.get(current, set())}
    if target not in allowed:
        names = ", ".join(sorted(allowed)) or "none"
        raise Invalid(f"A {what} that is {current} can become: {names}")


def _colleague(session: Session, actor: User, user_id, roles: set[OrgRole], classification: str, what: str,
               station=None) -> User:
    """A user of the actor's organisation, with a suitable role, enough clearance for the case, and (when the case's
    station is given) working at that station."""
    user = session.get(User, user_id)
    if user is None or not user.is_active or user.organization_id != actor.organization_id:
        raise Invalid(f"The {what} must be an active user of your organisation")
    if user.org_role not in roles:
        raise Invalid(f"The {what} must have one of these roles: {', '.join(sorted(r.value for r in roles))}")
    if classification not in sensitivities_up_to(user.clearance):
        raise Invalid(f"The {what}'s clearance is below this case's classification ({classification})")
    if station is not None and not works_at(user, station.id):
        raise Invalid(f"The {what} doesn't work at the case's police station ({station.code})")
    return user


def record_access(session: Session, *, family: CaseFamily, user_id, change: AuthorizationChange,
                  old: str | None, new: str | None, actor: User, reason: str) -> None:
    """A permanent access-history record (spec §12: membership changes are immutable access-history events)."""
    session.add(AuthorizationEvent(organization_id=family.organization_id, case_family_id=family.id, user_id=user_id,
                                   change=change.value, old_value=old, new_value=new, actor_id=actor.id, reason=reason))


# ---------------------------------------------------------------- folders


def check_folder_name(value: str) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip())
    if not 1 <= len(value) <= 100 or not FOLDER_NAME.fullmatch(value):
        raise Invalid(f"Invalid folder name '{value[:60]}': letters, digits, spaces and '.', '_' or '-', up to 100 characters")
    return value


def find_folder(session: Session, family: CaseFamily, name: str) -> CaseFolder | None:
    return session.scalar(select(CaseFolder).where(CaseFolder.case_family_id == family.id,
                                                   func.lower(CaseFolder.name) == (name or "").strip().lower()))


def folder_named(session: Session, family: CaseFamily, name: str) -> CaseFolder:
    folder = find_folder(session, family, name)
    if folder is None:
        raise Invalid(f"This case has no folder named '{(name or '')[:60]}'. Choose one of its folders, or ask the Investigator to add it")
    return folder


def ensure_folder(session: Session, family: CaseFamily, actor: User, name: str, *, system: bool = False) -> CaseFolder:
    """The folder with this name, made if the case doesn't have it yet (reports, imports and links make theirs; the case's own
    folders come from its type). Making one is a history entry."""
    folder = find_folder(session, family, name)
    if folder is None:
        last = session.scalar(select(func.max(CaseFolder.added_at)).where(CaseFolder.case_family_id == family.id))
        now = dt.datetime.now(dt.UTC)
        folder = CaseFolder(case_family_id=family.id, name=check_folder_name(name), system=system, added_by=actor.id,
                            added_at=max(now, last + dt.timedelta(microseconds=1)) if last else now)  # after the folders before it
        session.add(folder)
        session.flush()
        history.append(session, family, actor, HistoryKind.FOLDER_ADDED, f"Folder {folder.name} added", subject_type="folder",
                       subject_id=folder.id, details={"folder": folder.name, "system": system})
    return folder


def add_folder(session: Session, actor: User, family: CaseFamily, name: str) -> CaseFolder:
    """The Investigator who leads the case, or its supervisor, adds a folder. Folders are never renamed or removed."""
    family = _lock_family(session, family.id)
    found = rights(session, actor, family)
    require(found.add_folders, "Folders are added by the Investigator who leads the case, or by its supervisor", found)
    name = check_folder_name(name)
    if find_folder(session, family, name) is not None:
        raise Conflict(f"This case already has a folder named {name}")
    return ensure_folder(session, family, actor, name)


# ---------------------------------------------------------------- notes: artifacts and their versions


def _new_version(session: Session, *, family: CaseFamily, folder: CaseFolder | None, artifact: Artifact | None,
                 artifact_type: ArtifactType, title: str, content: dict, author: User, change_note: str | None = None,
                 derived_from: list[str] = ()) -> tuple[Artifact, ArtifactVersion]:
    """A new artifact (version 1, in `folder`) or a new version of an existing one. Earlier versions never change."""
    if artifact is None:
        prefix = ARTIFACT_PREFIX[artifact_type]
        count = session.scalar(select(func.count()).select_from(Artifact).where(
            Artifact.case_family_id == family.id, Artifact.display_id.like(f"{prefix}-%")))
        artifact = Artifact(case_family_id=family.id, folder_id=folder.id, display_id=f"{prefix}-{count + 1:04d}",
                            artifact_type=artifact_type.value, title=title, created_by=author.id,
                            created_at=dt.datetime.now(dt.UTC))  # the real clock: files list in the order they were made
        session.add(artifact)
        session.flush()
        number = 1
    else:
        number = 1 + session.scalar(select(func.max(ArtifactVersion.version_number)).where(ArtifactVersion.artifact_id == artifact.id))
    version = ArtifactVersion(artifact_id=artifact.id, version_number=number, content=content,
                              content_sha256=hashing.content_hash(content), derived_from=list(derived_from),
                              author_id=author.id, change_note=change_note)
    session.add(version)
    session.flush()
    return artifact, version


def latest_version(session: Session, artifact: Artifact) -> ArtifactVersion:
    return session.scalar(select(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact.id)
                          .order_by(ArtifactVersion.version_number.desc()).limit(1))


def resolve_sources(session: Session, user: User, family: CaseFamily, refs: list[str], *, exclude: Artifact | None = None) -> list[str]:
    """The version ids behind a note's `derived_from` file numbers (EV-0001, NOTE-0002): active files of this case the user can see."""
    if len(refs) > MAX_DERIVED_FROM:
        raise Invalid(f"At most {MAX_DERIVED_FROM} sources in derived_from")
    hidden = hidden_file_ids(session, user, family)
    found: list[str] = []
    for ref in refs:
        ref = (ref or "").strip().upper()
        artifact = session.scalar(select(Artifact).where(Artifact.case_family_id == family.id, Artifact.display_id == ref))
        item = None if artifact else session.scalar(select(EvidenceItem).where(EvidenceItem.case_family_id == family.id,
                                                                               EvidenceItem.display_id == ref))
        thing = artifact or item
        if thing is None or thing.status != FileStatus.ACTIVE.value or thing.id in hidden or (exclude and thing.id == exclude.id):
            raise Invalid(f"derived_from {ref[:60]} isn't an active file of this case")
        if artifact is not None:
            found.append(str(latest_version(session, artifact).id))
        else:  # the original version of the exhibit
            found.append(str(session.scalar(select(EvidenceVersion.id).where(EvidenceVersion.evidence_item_id == item.id))))
    return found


def _content(content: Any, what: str) -> dict:
    if not isinstance(content, dict) or len(hashing.canonical_json(content)) > MAX_CONTENT_BYTES:
        raise Invalid(f"{what}: content must be a JSON object of at most {MAX_CONTENT_BYTES:,} bytes")
    return content


def add_note(session: Session, actor: User, family: CaseFamily, *, folder: str, artifact_type: str, title: str, content: dict,
             derived_from: list[str] = (), note: str | None = None) -> tuple[Artifact, ArtifactVersion]:
    """Write a note, analysis, transcription or timeline in a folder of the case: it is part of the case at once."""
    family = _lock_family(session, family.id)
    found = rights(session, actor, family)
    require(found.add_files, "You can read this case but not add to it", found)
    try:
        kind = ArtifactType(artifact_type)
    except ValueError:
        raise Invalid(f"Unknown kind of file '{str(artifact_type)[:40]}'") from None
    if kind not in ADDABLE_TYPES:
        raise Invalid(f"People write these kinds of file: {', '.join(sorted(t.value for t in ADDABLE_TYPES))}")
    title = (title or "").strip()
    if not 3 <= len(title) <= 300:
        raise Invalid("A title of 3 to 300 characters is required")
    where = folder_named(session, family, folder)
    sources = resolve_sources(session, actor, family, list(derived_from))
    artifact, version = _new_version(session, family=family, folder=where, artifact=None, artifact_type=kind, title=title,
                                     content=_content(content, title), author=actor, change_note=note, derived_from=sources)
    history.append(session, family, actor, HistoryKind.NOTE_ADDED, f"{artifact.display_id} {title} added to {where.name}",
                   subject_type="artifact", subject_id=artifact.id,
                   details={"display_id": artifact.display_id, "folder": where.name, "type": kind.value, "version": 1,
                            "content_sha256": version.content_sha256})
    return artifact, version


def revise_note(session: Session, actor: User, family: CaseFamily, artifact: Artifact, *, content: dict, expected_version: int,
                note: str | None = None, derived_from: list[str] = ()) -> ArtifactVersion:
    """A new version of a note. The Investigator and the supervisor may revise any note; a Sub Investigator or Analyst only their own.
    `expected_version` is the version the new text was written from: if someone revised it since, nothing is overwritten (409)."""
    family = _lock_family(session, family.id, artifact)
    found = rights(session, actor, family)
    require(found.add_files, "You can read this case but not add to it", found)
    kind = ArtifactType(artifact.artifact_type)
    if kind in KEPT_AS_MADE:
        raise Invalid(f"{artifact.display_id} is {KEPT_AS_MADE[kind]}")
    if artifact.status != FileStatus.ACTIVE.value:
        raise Invalid(f"{artifact.display_id} was withdrawn")
    if artifact.sealed and not supervises(actor, family):
        raise NotVisible(exists=True)
    require(found.revise_any or artifact.created_by == actor.id,
            f"{artifact.display_id} is someone else's note: you may revise your own; the Investigator or the supervisor may revise any", found)
    current = latest_version(session, artifact)
    if expected_version != current.version_number:
        raise Conflict(f"{artifact.display_id} was changed since you opened it (it is now version {current.version_number}). "
                       "Reload and try again: nothing was overwritten.", current_version=current.version_number)
    sources = resolve_sources(session, actor, family, list(derived_from), exclude=artifact)
    _, version = _new_version(session, family=family, folder=None, artifact=artifact, artifact_type=kind, title=artifact.title,
                              content=_content(content, artifact.title), author=actor, change_note=(note or "").strip() or None,
                              derived_from=[str(current.id), *sources])
    folder = session.get(CaseFolder, artifact.folder_id)
    history.append(session, family, actor, HistoryKind.NOTE_REVISED,
                   f"{artifact.display_id} {artifact.title} revised (version {version.version_number})",
                   subject_type="artifact", subject_id=artifact.id,
                   details={"display_id": artifact.display_id, "folder": folder.name, "version": version.version_number,
                            "content_sha256": version.content_sha256})
    return version


def withdraw_file(session: Session, actor: User, family: CaseFamily, item: Artifact | EvidenceItem, *, reason: str) -> None:
    """A wrong file is withdrawn with a reason: it leaves the case's current view and stays in the history, and can't be deleted."""
    family = _lock_family(session, family.id, item)
    found = rights(session, actor, family)
    require(found.withdraw, "Only the Investigator who leads the case withdraws files: a supervisor sees them and removes nothing", found)
    if isinstance(item, Artifact) and ArtifactType(item.artifact_type) in NEVER_WITHDRAWN:
        raise Invalid(f"{item.display_id} is part of the registration record and can't be withdrawn")
    if item.status != FileStatus.ACTIVE.value:
        raise Invalid(f"{item.display_id} was already withdrawn")
    reason = _reason(reason)
    item.status, item.withdrawn_reason, item.withdrawn_by = FileStatus.WITHDRAWN.value, reason, actor.id
    item.withdrawn_at = dt.datetime.now(dt.UTC)
    session.flush()
    folder = session.get(CaseFolder, item.folder_id)
    history.append(session, family, actor, HistoryKind.FILE_WITHDRAWN, f"{item.display_id} {item.title} withdrawn from {folder.name}: {reason}",
                   subject_type="evidence" if isinstance(item, EvidenceItem) else "artifact", subject_id=item.id,
                   details={"display_id": item.display_id, "folder": folder.name, "reason": reason})


# ---------------------------------------------------------------- cases


def case_type_folders(code: str) -> list[str]:
    return list(case_type(code)["folders"])


def _reporter(reported_by: dict | None) -> dict:
    """The columns for who reported the case: blank entries are nothing; "unknown" and details never go together."""
    given = {k: ((reported_by or {}).get(k) or "").strip() or None for k in ("name", "phone", "email", "address")}
    unknown = bool((reported_by or {}).get("unknown")) and not any(given.values())
    return {"reported_by_unknown": unknown, **{f"reported_by_{k}": v for k, v in given.items()}}


def create_case(session: Session, actor: User, *, title: str, case_type: str, description: str, priority: str,
                description_html: str | None = None, classification: str, jurisdiction: str | None = None, lead_id=None, supervisor_id=None,
                official_reference: dict | None = None, station_id=None, reported_by: dict | None = None) -> CreatedCase:
    """Register a case: the case, its folders (made at once from the case's type), the Investigator who leads it, the case summary,
    and the first entry of its history."""
    if actor.organization_id is None or actor.org_role not in CASE_CREATORS:
        raise Forbidden("Your role can't create cases")
    organization = session.scalar(select(Organization).where(Organization.id == actor.organization_id).with_for_update())
    station = station_for_new_case(session, actor, station_id)
    lead = _colleague(session, actor, lead_id or actor.id, LEAD_CAPABLE, classification, "lead investigator", station)
    supervisor = _colleague(session, actor, supervisor_id, SUPERVISING, classification, "supervisor", station) if supervisor_id else None

    year = dt.datetime.now(dt.UTC).year
    sequence = 1 + (session.scalar(select(func.max(CaseFamily.sequence)).where(
        CaseFamily.organization_id == organization.id, CaseFamily.year == year)) or 0)
    family = CaseFamily(
        organization_id=organization.id, station_id=station.id, display_id=f"{organization.code}-{year}-{sequence:04d}", year=year,
        sequence=sequence, title=title, case_type=case_type, description=description, description_html=rich_text.clean(description_html), priority=priority,
        classification=classification, jurisdiction=jurisdiction, supervisor_id=supervisor.id if supervisor else None,
        created_by=actor.id, workflow_status=WorkflowStatus.REGISTERED.value, **_reporter(reported_by),
        created_at=dt.datetime.now(dt.UTC),  # the real clock: the promotion rule compares it with the date a role took effect
    )
    session.add(family)
    session.flush()

    # The folders of the case, made at once from its type.
    names = list(dict.fromkeys(case_type_folders(case_type)))
    if INFORMATION_FOLDER not in names:
        names.insert(0, INFORMATION_FOLDER)
    # Each folder has its own moment, a microsecond apart, so they list in the order of the case type (a request has one clock).
    first = dt.datetime.now(dt.UTC)
    folders = [CaseFolder(case_family_id=family.id, name=name, added_by=actor.id, added_at=first + dt.timedelta(microseconds=i))
               for i, name in enumerate(names)]
    session.add_all(folders)
    session.flush()
    information = next(f for f in folders if f.name == INFORMATION_FOLDER)

    summary = {"title": title, "case_type": case_type, "description": description, "priority": priority,
               "classification": classification, "jurisdiction": jurisdiction}
    _, summary_version = _new_version(session, family=family, folder=information, artifact=None, artifact_type=ArtifactType.CASE_SUMMARY,
                                      title="Case summary", content=summary, author=actor)
    made = ["SUM-0001"]
    if official_reference:
        session.add(CaseOfficialReference(case_family_id=family.id, recorded_by=actor.id, **official_reference))
        reference = {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in official_reference.items()}
        _new_version(session, family=family, folder=information, artifact=None, artifact_type=ArtifactType.OFFICIAL_REFERENCES,
                     title="Official references", content={"references": [reference]}, author=actor)
        made.append("REF-0001")

    session.add(CaseMember(case_family_id=family.id, user_id=lead.id, role=MemberRole.LEAD.value, granted_by=actor.id))
    record_access(session, family=family, user_id=lead.id, change=AuthorizationChange.MEMBERSHIP_GRANTED, old=None,
                  new=MemberRole.LEAD.value, actor=actor, reason=f"Investigator leading {family.display_id}")
    session.add(CaseStatusEvent(case_family_id=family.id, field=StatusField.WORKFLOW.value, old_value=None,
                                new_value=WorkflowStatus.REGISTERED.value, actor_id=actor.id, reason="Case created"))
    history.append(session, family, actor, HistoryKind.CASE_REGISTERED, f"Case {family.display_id} registered: {title}",
                   subject_type="case", subject_id=family.id,
                   details={"case_type": case_type, "station": station.code, "lead": lead.username, "folders": names, "files": made,
                            "summary_sha256": summary_version.content_sha256})
    notify(session, [lead.id], "case.assigned", family=family, actor=actor, title=title)
    return CreatedCase(family, folders, lead)


# ---------------------------------------------------------------- statuses

W = WorkflowStatus
WORKFLOW_TRANSITIONS = {
    W.REGISTERED: {W.OPEN, W.UNDER_INVESTIGATION},
    W.OPEN: {W.UNDER_INVESTIGATION, W.CLOSED},
    W.UNDER_INVESTIGATION: {W.PENDING_EVIDENCE, W.PENDING_REVIEW, W.INVESTIGATION_COMPLETED},
    W.PENDING_EVIDENCE: {W.UNDER_INVESTIGATION},
    W.PENDING_REVIEW: {W.UNDER_INVESTIGATION, W.APPROVED_FOR_REPORTING},
    W.APPROVED_FOR_REPORTING: {W.UNDER_INVESTIGATION, W.INVESTIGATION_COMPLETED},
    W.INVESTIGATION_COMPLETED: {W.UNDER_INVESTIGATION, W.CLOSED},
    W.CLOSED: {W.ARCHIVED, W.REOPENED},
    W.ARCHIVED: {W.REOPENED},
    W.REOPENED: {W.UNDER_INVESTIGATION},
}
SUPERVISOR_DECISIONS = {W.CLOSED, W.ARCHIVED, W.REOPENED}  # the lead handles the rest of the workflow


def change_case_status(session: Session, actor: User, family: CaseFamily, *, field: str, value: str, reason: str) -> None:
    """The internal workflow status (allowed transitions only) or the official police status (as recorded officially).

    Changing a case's status never closes, changes or deletes any file or history entry.
    """
    family = _lock_family(session, family.id, family)
    reason = _reason(reason)
    if field == StatusField.WORKFLOW:
        if value not in set(WorkflowStatus):
            raise Invalid(f"Unknown workflow status '{value}'")
        _allowed(family.workflow_status, value, WORKFLOW_TRANSITIONS, "case")
        if value in SUPERVISOR_DECISIONS and not supervises(actor, family):
            raise Forbidden(f"Only the supervisor or an administrator can set a case to {value}")
        if value in SUPERVISOR_DECISIONS:
            require_strong_auth(actor, f"setting a case to {value}")
        if value == WorkflowStatus.ARCHIVED:
            from app.casemgmt.governance.holds import ensure_not_held  # here: the holds module needs this one
            ensure_not_held(session, family, "archiving the case")
        if not (supervises(actor, family) or is_case_lead(session, actor, family)):
            raise Forbidden("Only the Investigator who leads the case, the supervisor or an administrator can change the workflow status")
        old, family.workflow_status = family.workflow_status, value
    elif field == StatusField.OFFICIAL:
        if not supervises(actor, family):
            raise Forbidden("The official status is recorded by the supervisor or an administrator, from an official source")
        require_strong_auth(actor, "recording the official status")
        value = (value or "").strip()
        if not 1 <= len(value) <= 64:
            raise Invalid("The official status is 1 to 64 characters, as written in the official record")
        old, family.official_status = family.official_status, value
    else:
        raise Invalid("Only a case's workflow or official status is changed here")
    session.add(CaseStatusEvent(case_family_id=family.id, field=StatusField(field).value, old_value=old, new_value=value,
                                actor_id=actor.id, reason=reason))
    session.flush()
    label = "Status" if field == StatusField.WORKFLOW else "Official status"
    history.append(session, family, actor, HistoryKind.STATUS_CHANGED, f"{label} changed from {old or 'none'} to {value}: {reason}",
                   subject_type="case", subject_id=family.id, details={"field": field, "old": old, "new": value, "reason": reason})


CASE_NUMBER = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ./_-]{2,31}")


def check_case_number(session: Session, family: CaseFamily, value: str | None) -> str:
    """A case number somebody typed: 3 to 32 letters, digits, spaces and . / _ -, not the case's own, not another case's (now or before).

    The numbers the system hands out itself (CODE-YEAR-0001) are not accepted, so a later case can never be given one that is taken;
    the case's own automatic number is the one exception (it may go back to it)."""
    number = re.sub(r"\s+", " ", (value or "").strip())
    if not CASE_NUMBER.fullmatch(number):
        raise Invalid("A case number is 3 to 32 letters, digits, spaces or . / _ - (it starts with a letter or digit)")
    organization = session.get(Organization, family.organization_id)
    own_automatic = f"{organization.code}-{family.year}-{family.sequence:04d}"
    if number.upper() == family.display_id.upper():
        raise Invalid(f"{family.display_id} is already the number of this case")
    taken = session.scalar(select(CaseFamily.id).where(CaseFamily.organization_id == family.organization_id,
                                                      func.upper(CaseFamily.display_id) == number.upper(), CaseFamily.id != family.id))
    used_before = session.scalar(select(CaseNumberChange.id).where(
        CaseNumberChange.organization_id == family.organization_id, func.upper(CaseNumberChange.old_number) == number.upper(),
        CaseNumberChange.case_family_id != family.id).limit(1))
    if taken or used_before:
        raise Conflict(f"The number {number} is used by another case (or was): choose another")
    if re.fullmatch(rf"{re.escape(organization.code)}-\d{{4}}-\d{{4}}", number, re.IGNORECASE) and number.upper() != own_automatic.upper():
        raise Invalid(f"Numbers like {organization.code}-YYYY-NNNN are given by the system to new cases: choose another number")
    return number


def change_case_number(session: Session, actor: User, family: CaseFamily, *, number: str, reason: str) -> str:
    """Whoever oversees the case changes its number. The old number is kept (still finds the case, never reused) and the change is a
    numbered entry of the history, with who and why. Nothing else about the case changes."""
    family = _lock_family(session, family.id, family)
    found = rights(session, actor, family)
    require(found.rename_case, "The case number is changed by the case's supervisor or an administrator", found)
    require_strong_auth(actor, "changing the case number")
    reason = _reason(reason)
    new = check_case_number(session, family, number)
    old, family.display_id = family.display_id, new
    session.add(CaseNumberChange(case_family_id=family.id, organization_id=family.organization_id, old_number=old, new_number=new,
                                 reason=reason, changed_by=actor.id))
    session.flush()
    history.append(session, family, actor, HistoryKind.CASE_RENUMBERED, f"Case number changed from {old} to {new}: {reason}",
                   subject_type="case", subject_id=family.id, details={"old": old, "new": new, "reason": reason})
    return new


def change_case_name(session: Session, actor: User, family: CaseFamily, *, name: str, reason: str) -> str:
    """Rename the case's title. Only the supervisor or an administrator may do this."""
    family = _lock_family(session, family.id, family)
    found = rights(session, actor, family)
    require(found.rename_case, "The case name can only be changed by the case's supervisor or an administrator", found)
    name = name.strip()
    if len(name) < 3 or len(name) > 300:
        raise Invalid("Case name must be between 3 and 300 characters")
    reason = _reason(reason)
    old_name = family.title
    family.title = name
    session.flush()
    history.append(session, family, actor, HistoryKind.CASE_RENUMBERED,
                   f"Case name changed from '{old_name}' to '{name}': {reason}",
                   subject_type="case", subject_id=family.id,
                   details={"old_name": old_name, "new_name": name, "reason": reason})
    return name


def add_official_reference(session: Session, actor: User, family: CaseFamily, *, ref_type: str, number: str,
                           issuing_authority: str | None, ref_date: dt.date | None, source: str) -> CaseOfficialReference:
    """Record an official reference (FIR, complaint, court case number). References are added, never edited."""
    family = _lock_family(session, family.id)
    if not supervises(actor, family):
        raise Forbidden("Official references are recorded by the supervisor or an administrator")
    duplicate = session.scalar(select(CaseOfficialReference.id).where(
        CaseOfficialReference.case_family_id == family.id, func.lower(CaseOfficialReference.ref_type) == ref_type.lower(),
        CaseOfficialReference.number == number))
    if duplicate:
        raise Conflict(f"{ref_type} {number} is already recorded for {family.display_id}")
    reference = CaseOfficialReference(case_family_id=family.id, ref_type=ref_type, number=number, issuing_authority=issuing_authority,
                                      ref_date=ref_date, source=source, recorded_by=actor.id)
    session.add(reference)
    session.flush()
    history.append(session, family, actor, HistoryKind.REFERENCE_ADDED, f"{ref_type} {number} recorded",
                   subject_type="reference", subject_id=reference.id, details={"ref_type": ref_type, "number": number, "source": source})
    return reference
