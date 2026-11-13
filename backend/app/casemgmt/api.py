"""Case Management API under /api/v1 (docs/case-management/06-api-contracts.md, 13-plain-case-design.md).

- Access is checked inside the database query of every request (access.py). What a user may not see
  answers 404, exactly like something that doesn't exist, and the attempt is audited.
- A write and its audit event are committed together: both are saved, or neither is. A refused or failed
  request is rolled back and still audited, in its own transaction.
- There are no DELETE routes. DELETE, PUT and PATCH anywhere under /api/v1, and history-rewriting actions
  such as reset or rebase, answer 405 and are audited.
"""

import re
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.log import AuditLog, fingerprint, get_audit_log
from app.auth.dependencies import CurrentUser
from app.casemgmt import engine, files, history, members, queries
from app.casemgmt import schemas as s
from app.casemgmt.access import get_family, is_super_admin
from app.casemgmt.case_types import CASE_TYPES, EVIDENCE_TYPES
from app.casemgmt.errors import CaseManagementError, Conflict, Forbidden, Invalid, NotVisible
from app.casemgmt.idempotency import Once
from app.casemgmt.models import CaseFamily, EvidenceItem
from app.core.enums import AuditOutcome
from app.db.models import AuditEvent, User
from app.db.session import get_db

router = APIRouter(prefix="/v1", tags=["case management"])
DbSession = Annotated[Session, Depends(get_db)]
Audit = Annotated[AuditLog, Depends(get_audit_log)]
Limit = Annotated[int, Query(ge=1, le=200)]
Cursor = Annotated[str | None, Query(max_length=64)]
Text = Annotated[str | None, Query(max_length=200)]
# Create requests may carry this header: repeating a request with the same key returns the first answer (idempotency.py).
IdempotencyKeyHeader = Annotated[str | None, Header(alias="Idempotency-Key", max_length=100)]


class Audited:
    """The audit trail of one request.

    with Audited(db, audit, user, "cm.x", "cm_case", case_id) as event:
        ... event.target_id = family.display_id ... event.read() or event.write()
    """

    def __init__(self, db: Session, audit: AuditLog, user: User, action: str, target_type: str, target_id: Any = None, **details):
        self.db, self.audit, self.user, self.action, self.target_type = db, audit, user, action, target_type
        self.target_id, self.details = target_id, details

    def __enter__(self) -> "Audited":
        return self

    def __exit__(self, kind, exc, traceback) -> bool:
        if isinstance(exc, IntegrityError):  # a race with another request, or a database rule (trigger) refused it
            self.db.rollback()
            self._record(self.audit, AuditOutcome.REJECTED, self.action, refused="IntegrityError",
                         constraint=getattr(getattr(exc.orig, "diag", None), "constraint_name", None))
            self.db.commit()
            raise Conflict("The case changed while this was being saved, or the change isn't allowed. "
                           "Nothing was saved: reload and try again.") from exc
        if isinstance(exc, CaseManagementError):
            self.db.rollback()  # nothing of a refused request is kept...
            if isinstance(exc, NotVisible):
                outcome = AuditOutcome.DENIED if exc.extra.get("exists") else AuditOutcome.NOT_FOUND
            else:
                outcome = AuditOutcome.DENIED if isinstance(exc, Forbidden) else AuditOutcome.REJECTED
            self._record(self.audit, outcome, self.action, refused=type(exc).__name__)
            self.db.commit()  # ...except its audit event (already in its own transaction outside tests)
        return False

    def _record(self, log: AuditLog, outcome: AuditOutcome, action: str, *, target_type: str | None = None,
                target_id: Any = None, **details) -> None:
        target = target_id if target_id is not None else self.target_id
        log.record(action, outcome, user=self.user, target_type=target_type or self.target_type,
                   target_id=str(target)[:128] if target is not None else None,
                   details=jsonable_encoder({k: v for k, v in {**self.details, **details}.items() if v is not None}))

    def read(self, **details) -> None:
        self._record(self.audit, AuditOutcome.SUCCESS, self.action, **details)
        self.db.commit()  # ends the read-only transaction

    def error(self, **details) -> None:
        """Record a failure that isn't the user's (e.g. the AI model is down). What the request saved so far is kept."""
        self._record(self.audit, AuditOutcome.ERROR, self.action, **details)
        self.db.commit()

    def write(self, *, also: list[dict] = (), **details) -> None:
        """Record the success, plus any further events, in the same transaction as the change; then commit."""
        log = AuditLog(client_ip=self.audit.client_ip, session=self.db)
        self._record(log, AuditOutcome.SUCCESS, self.action, **details)
        for event in also:
            self._record(log, AuditOutcome.SUCCESS, **event)
        self.db.commit()


def _offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isdigit():
        raise Invalid("Invalid cursor")
    return int(cursor)


def _next(offset: int, limit: int, total: int) -> str | None:
    return str(offset + limit) if offset + limit < total else None


def _require_admin(user: User) -> None:
    if not is_super_admin(user):
        raise Forbidden("Only platform administrators can use the administration views")


# ---------------------------------------------------------------- case registry


@router.get("/case-types", response_model=list[s.CaseType])
def list_case_types(_user: CurrentUser) -> list[dict]:
    return [{"code": code, "label": t["label"], "folders": t["folders"], "evidence_types": EVIDENCE_TYPES}
            for code, t in CASE_TYPES.items()]


@router.post("/cases", response_model=s.CaseCreated, status_code=status.HTTP_201_CREATED)
def create_case(body: s.CaseCreate, user: CurrentUser, db: DbSession, audit: Audit,
                idempotency_key: IdempotencyKeyHeader = None) -> dict:
    with Audited(db, audit, user, "cm.case.created", "cm_case", case_type=body.case_type,
                 classification=body.classification) as event:
        once = Once(db, user, idempotency_key, "POST /api/v1/cases", body.model_dump(mode="json"))
        if (previous := once.previous()) is not None:
            event.read(replayed=True)
            return previous
        created = engine.create_case(
            db, user, title=body.title, case_type=body.case_type, description=body.description, description_html=body.description_html, priority=body.priority.value,
            classification=body.classification.value, jurisdiction=body.jurisdiction, lead_id=body.lead_investigator_id,
            supervisor_id=body.supervisor_id, station_id=body.station_id,
            official_reference=body.official_reference.model_dump() if body.official_reference else None,
            reported_by=body.reported_by.model_dump() if body.reported_by else None,
        )
        event.target_id = created.family.display_id
        lead = queries.people(db, [created.lead.id])[created.lead.id]
        result = {"case_id": created.family.id, "display_id": created.family.display_id,
                  "folders": [f.name for f in created.folders], "lead": lead}
        once.save(status.HTTP_201_CREATED, s.CaseCreated, result)
        event.write(folders=len(created.folders), lead=created.lead.id)
    return result


@router.get("/cases", response_model=s.CaseList)
def list_cases(user: CurrentUser, db: DbSession, audit: Audit, limit: Limit = 50, cursor: Cursor = None, q: Text = None,
               workflow_status: Text = None, case_type: Text = None) -> dict:
    with Audited(db, audit, user, "cm.cases.list", "cm_case") as event:
        offset = _offset(cursor)
        items, total = queries.list_cases(db, user, limit=limit, offset=offset, q=q, workflow_status=workflow_status,
                                          case_type_code=case_type)
        event.read(count=len(items), query_fingerprint=fingerprint(q) if q else None)
    return {"items": items, "total": total, "next_cursor": _next(offset, limit, total)}


@router.get("/cases/mine", response_model=list[s.MyCase])
def my_cases(user: CurrentUser, db: DbSession, audit: Audit) -> list[dict]:
    """The cases you are on the team of, with your part in each (the investigator's "My cases")."""
    with Audited(db, audit, user, "cm.cases.mine", "cm_case") as event:
        found = queries.my_cases(db, user)
        event.read(count=len(found))
    return found


@router.get("/cases/{case_id}", response_model=s.CaseDetail)
def case_detail(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.case.view", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        detail = queries.case_detail(db, user, family)
        event.read()
    return detail


@router.post("/cases/{case_id}/official-references", response_model=s.OfficialReferenceOut, status_code=status.HTTP_201_CREATED)
def add_official_reference(case_id: uuid.UUID, body: s.OfficialReferenceIn, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.reference.added", "cm_case", case_id, ref_type=body.ref_type) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        ref = engine.add_official_reference(db, user, family, **body.model_dump())
        result = {"id": ref.id, "ref_type": ref.ref_type, "number": ref.number, "issuing_authority": ref.issuing_authority,
                  "ref_date": ref.ref_date, "source": ref.source, "recorded_by": queries.people(db, [user.id])[user.id],
                  "recorded_at": ref.recorded_at}
        event.write()
    return result


@router.post("/cases/{case_id}/status", response_model=s.CaseDetail)
def change_case_status(case_id: uuid.UUID, body: s.CaseStatusChange, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.case.status_changed", "cm_case", case_id, field=body.field, value=body.value) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        engine.change_case_status(db, user, family, field=body.field, value=body.value, reason=body.reason)
        event.write()
    return queries.case_detail(db, user, family)


@router.post("/cases/{case_id}/number", response_model=s.CaseDetail)
def change_case_number(case_id: uuid.UUID, body: s.CaseNumberChange, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Change the case's number (the supervisor or an administrator). The old number is kept, still finds the case, and is never reused."""
    with Audited(db, audit, user, "cm.case.renumbered", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        old = family.display_id
        event.target_id = old
        new = engine.change_case_number(db, user, family, number=body.number, reason=body.reason)
        event.write(old=old, new=new)
    return queries.case_detail(db, user, family)


@router.post("/cases/{case_id}/name", response_model=s.CaseDetail)
def change_case_name(case_id: uuid.UUID, body: s.CaseNameChange, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Rename the case (supervisor or administrator only). The old name and reason are recorded in the case history."""
    with Audited(db, audit, user, "cm.case.renamed", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        new_name = engine.change_case_name(db, user, family, name=body.name, reason=body.reason)
        event.write(new_name=new_name)
    return queries.case_detail(db, user, family)


# ---------------------------------------------------------------- folders, files and notes


@router.get("/cases/{case_id}/folders", response_model=list[s.FolderOut])
def list_folders(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> list[dict]:
    with Audited(db, audit, user, "cm.folders.list", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        found = queries.folders_of(db, user, family)
        event.read(count=len(found))
    return found


@router.post("/cases/{case_id}/folders", response_model=s.FolderOut, status_code=status.HTTP_201_CREATED)
def add_folder(case_id: uuid.UUID, body: s.FolderCreate, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Add a folder to the case (the Investigator who leads it, or its supervisor). Folders are never renamed or removed."""
    with Audited(db, audit, user, "cm.folder.added", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        folder = engine.add_folder(db, user, family, body.name)
        result = next(f for f in queries.folders_of(db, user, family) if f["id"] == folder.id)
        event.write(folder=folder.name)
    return result


@router.get("/cases/{case_id}/files", response_model=s.FilesView)
def list_files(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit, folder: Text = None,
               include_withdrawn: bool = False) -> dict:
    """The case's files (exhibits and notes), in one folder or in all. A withdrawn file shows only when asked for."""
    with Audited(db, audit, user, "cm.files.list", "cm_case", case_id, folder=folder) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        result = files.view(db, user, family, folder=folder, include_withdrawn=include_withdrawn)
        event.read(count=len(result["files"]))
    return result


@router.post("/cases/{case_id}/notes", response_model=s.NoteAdded, status_code=status.HTTP_201_CREATED)
def add_note(case_id: uuid.UUID, body: s.NoteCreate, user: CurrentUser, db: DbSession, audit: Audit,
             idempotency_key: IdempotencyKeyHeader = None) -> dict:
    """Write a note, analysis, transcription or timeline in a folder of the case. It is part of the case at once."""
    with Audited(db, audit, user, "cm.note.added", "cm_case", case_id, folder=body.folder, type=body.artifact_type) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        once = Once(db, user, idempotency_key, f"POST /api/v1/cases/{case_id}/notes", body.model_dump(mode="json"))
        if (previous := once.previous()) is not None:
            event.read(replayed=True)
            return previous
        artifact, version = engine.add_note(db, user, family, folder=body.folder, artifact_type=body.artifact_type, title=body.title,
                                            content=body.content, derived_from=body.derived_from, note=body.note)
        entry = history.last_entry(db, family.id)
        row = next(r for r in files.files(db, user, family, folder=body.folder) if r["id"] == artifact.id)
        result = {"file": row, "entry": entry.seq}
        once.save(status.HTTP_201_CREATED, s.NoteAdded, result)
        event.write(artifact=artifact.display_id, entry=entry.seq, sha256=version.content_sha256)
    return result


# ---------------------------------------------------------------- history


@router.get("/cases/{case_id}/history", response_model=s.HistoryView)
def case_history(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit,
                 limit: Annotated[int, Query(ge=1, le=500)] = 100, after: Annotated[int | None, Query(ge=0)] = None,
                 latest: Annotated[int | None, Query(ge=1, le=50, description="Only the newest entries (oldest of them first)")] = None) -> dict:
    """Everything that happened in the case, oldest first (permanent)."""
    with Audited(db, audit, user, "cm.history.read", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        result = queries.history_view(db, family, limit=limit, after=after, latest=latest)
        event.read(count=len(result["entries"]))
    return result


@router.get("/cases/{case_id}/history/check", response_model=s.HistoryCheck)
def check_history(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Re-check the case's whole history: every entry is recomputed and must follow the one before it."""
    with Audited(db, audit, user, "cm.history.checked", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        result = history.verify_chain(db, family.id)
        event.read(intact=result["intact"], entries=result["entries"])
    return result


# ---------------------------------------------------------------- the team


@router.get("/cases/{case_id}/team", response_model=s.TeamView)
def case_team(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.team.read", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        result = {"case": queries.case_ref(family), "team": queries.team_rows(db, family)}
        event.read(count=len(result["team"]))
    return result


@router.post("/cases/{case_id}/team", response_model=s.TeamView, status_code=status.HTTP_201_CREATED)
def add_team_member(case_id: uuid.UUID, body: s.TeamAdd, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Add a Sub Investigator, Analyst or Viewer to the case: at once, no invitation to accept (the Investigator who leads the
    case, its supervisor or an administrator)."""
    with Audited(db, audit, user, "cm.team.added", "cm_case", case_id, person=body.user_id, role=body.role) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        members.add_member(db, user, family, user_id=body.user_id, role=body.role)
        result = {"case": queries.case_ref(family), "team": queries.team_rows(db, family)}
        event.write()
    return result


@router.post("/cases/{case_id}/team/{member_id}/remove", response_model=s.TeamView)
def remove_team_member(case_id: uuid.UUID, member_id: uuid.UUID, body: s.RequiredReason, user: CurrentUser, db: DbSession,
                       audit: Audit) -> dict:
    """End someone's place on the team. Everything they did stays attributed to them."""
    with Audited(db, audit, user, "cm.team.removed", "cm_case", case_id, person=member_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        removed = members.remove_member(db, user, family, member_id, body.reason)
        result = {"case": queries.case_ref(family), "team": queries.team_rows(db, family)}
        event.write(role=removed.role)
    return result


@router.post("/cases/{case_id}/lead", response_model=s.CaseDetail)
def hand_over_case(case_id: uuid.UUID, body: s.LeadChange, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Hand the case to another Investigator (the supervisor or an administrator decides). The old lead stays as a Sub Investigator."""
    with Audited(db, audit, user, "cm.case.lead_changed", "cm_case", case_id, person=body.user_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        members.change_lead(db, user, family, user_id=body.user_id, reason=body.reason)
        event.write()
    return queries.case_detail(db, user, family)


# ---------------------------------------------------------------- administration


@router.get("/admin/cases", response_model=s.Registry)
def admin_cases(user: CurrentUser, db: DbSession, audit: Audit, limit: Limit = 50, cursor: Cursor = None, q: Text = None,
                workflow_status: Text = None) -> dict:
    with Audited(db, audit, user, "cm.admin.registry", "cm_case") as event:
        _require_admin(user)
        offset = _offset(cursor)
        items, total = queries.admin_registry(db, user, limit=limit, offset=offset, q=q, workflow_status=workflow_status)
        event.read(count=len(items), query_fingerprint=fingerprint(q) if q else None)
    return {"items": items, "total": total, "next_cursor": _next(offset, limit, total)}


@router.get("/admin/cases/{case_id}/audit", response_model=s.CaseAudit)
def admin_case_audit(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit, limit: Limit = 100,
                     cursor: Cursor = None, show: Annotated[Literal["all", "refused"], Query(
                         description="`refused`: only what was refused or denied (deletions, rewrites, access to what someone "
                                     "may not see, rule violations), among every read and change")] = "all") -> dict:
    """The case's audit trail: every Case Management event about the case."""
    with Audited(db, audit, user, "cm.admin.audit", "cm_case", case_id, show=show if show != "all" else None) as event:
        _require_admin(user)
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        about_case = [AuditEvent.action.startswith("cm."),
                      or_(AuditEvent.target_id == family.display_id,
                          AuditEvent.target_id.startswith(f"{family.display_id}-", autoescape=True),
                          AuditEvent.target_id.startswith(f"{family.display_id}/", autoescape=True),  # its evidence
                          AuditEvent.target_id == str(family.id))]
        if show == "refused":
            about_case.append(AuditEvent.outcome != AuditOutcome.SUCCESS)
        offset = _offset(cursor)
        total = db.scalar(select(func.count()).select_from(AuditEvent).where(*about_case))
        items = list(db.scalars(select(AuditEvent).where(*about_case).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
                                .limit(limit).offset(offset)))
        result = {"items": [s.AuditEntry.model_validate(e) for e in items], "total": total, "next_cursor": _next(offset, limit, total)}
        event.read()
    return result


# ---------------------------------------------------------------- no deletion, no rewriting (docs/case-management/04 §9)

HISTORY_REWRITES = {"delete", "remove", "purge", "destroy", "erase", "drop", "truncate", "reset", "rebase", "squash", "amend",
                    "rewrite", "overwrite", "force-push", "force_push", "filter-branch"}
UUID_IN_PATH = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _reject(path: str, request: Request, user: User, db: Session, audit: AuditLog) -> JSONResponse:
    """405 for every deletion or history rewrite, recorded against the case or exhibit it aimed at (if any)."""
    target_type, target_id = "endpoint", f"{request.method} /api/v1/{path}"[:128]
    for found in UUID_IN_PATH.findall(path.lower())[:2]:
        key = uuid.UUID(found)
        thing = db.get(CaseFamily, key) or db.get(EvidenceItem, key)
        if isinstance(thing, EvidenceItem):
            target_type, target_id = "cm_evidence", f"{db.get(CaseFamily, thing.case_family_id).display_id}/{thing.display_id}"
            break
        if thing is not None:
            target_type, target_id = "cm_case", thing.display_id
            break
    audit.record("cm.destructive_operation.rejected", AuditOutcome.REJECTED, user=user, target_type=target_type,
                 target_id=target_id, details={"method": request.method, "path": f"/api/v1/{path}"[:300]})
    return JSONResponse(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED, headers={"Allow": "GET, POST"},
        content={"detail": "Case history is permanent: nothing can be deleted, overwritten or rewritten. Add a new version of a "
                           "note, or withdraw a file with a reason."},
    )


@router.api_route("/{path:path}", methods=["DELETE", "PUT", "PATCH"], include_in_schema=False)
def reject_destructive(path: str, request: Request, user: CurrentUser, db: DbSession, audit: Audit) -> JSONResponse:
    return _reject(path, request, user, db, audit)


@router.post("/{path:path}", include_in_schema=False)
def reject_rewrites(path: str, request: Request, user: CurrentUser, db: DbSession, audit: Audit) -> JSONResponse:
    """Registered last: real POST routes match first. History-rewriting verbs get 405; anything else doesn't exist."""
    if HISTORY_REWRITES & set(path.lower().split("/")):
        return _reject(path, request, user, db, audit)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
