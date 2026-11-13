"""Evidence endpoints under /api/v1 (docs/case-management/06, "Evidence and artifacts"; docs/case-management/13).

The same rules as the rest of the module (api.py): access is checked inside the queries, anything a user may
not see answers 404 exactly like something missing, every request is audited, and nothing can be deleted.
This router is included before the module's main router, whose catch-all answers 405 to DELETE, PUT, PATCH
and history-rewriting actions on these paths too.

Downloads use a link that works once, for 5 minutes, for the person it was made for, without the login
header (so a browser can follow it). Access is checked again when it is used, and the file's fingerprint is
recomputed first: a file that no longer matches is never sent.
"""

import re
import uuid
from collections.abc import Callable
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Path, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.casemgmt import custody, engine, evidence, evidence_views, queries
from app.casemgmt import schemas as s
from app.casemgmt.access import get_family
from app.casemgmt.api import Audit, Audited, Cursor, DbSession, IdempotencyKeyHeader, Limit, Text, _next, _offset, _require_admin
from app.casemgmt.enums import FileCategory, IntegrityResult, IntegrityTrigger
from app.casemgmt.errors import Conflict, Gone, NotVisible
from app.casemgmt.evidence import Seen
from app.casemgmt.idempotency import Once
from app.casemgmt.intelligence import index as text_index
from app.casemgmt.models import CaseFamily, CustodyEvent, IntegrityCheck
from app.casemgmt.storage import EvidenceStore, get_evidence_store
from app.core.config import get_settings
from app.db.models import User
from app.db.session import get_session_factory
from app.documents.extract import DOCX_MIME, ExtractionError, extract_known
from app.embeddings.model import Embedder, get_embedder

router = APIRouter(prefix="/v1", tags=["case management: evidence"])
Store = Annotated[EvidenceStore, Depends(get_evidence_store)]
PREVIEW_MAX_BYTES = 25 * 1024 * 1024
PREVIEW_MAX_CHARS = 200_000
CUSTODY_ACTIONS = {"transfer": "cm.custody.transferred", "acknowledge": "cm.custody.acknowledged", "decline": "cm.custody.declined"}


def label(seen: Seen) -> str:
    """How an exhibit is named in the audit log: case number / exhibit number (never its file name)."""
    return f"{seen.family.display_id}/{seen.item.display_id}"


def _seen(db: Session, user: User, evidence_id, event: Audited) -> Seen:
    seen = evidence.get_evidence(db, user, evidence_id)
    event.target_id = label(seen)
    return seen


def _intact(db: Session, store: EvidenceStore, seen: Seen, user: User, trigger: IntegrityTrigger) -> IntegrityCheck:
    """Recompute the fingerprint before content is shown or sent. A failure is kept, and the request refused."""
    check = evidence.check_object(db, store, seen.obj, actor=user, trigger=trigger, item_id=seen.item.id)
    if check.result != IntegrityResult.MATCH:
        db.commit()  # the failed check stays on record although the request is refused
        raise Conflict("The stored file doesn't match the fingerprint recorded when it was added, or is missing, so it was "
                       "not opened. This is recorded for the administrators (evidence integrity).", integrity=check.result)
    return check


def _attachment(filename: str) -> str:
    plain = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "evidence"
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(filename)}"


# ---------------------------------------------------------------- adding and listing evidence


@router.post("/cases/{case_id}/evidence", response_model=s.EvidenceAdded, status_code=status.HTTP_201_CREATED)
def add_evidence(case_id: uuid.UUID, form: Annotated[s.EvidenceUploadForm, Form()], user: CurrentUser, db: DbSession,
                 audit: Audit, store: Store, background: BackgroundTasks,
                 embedder: Annotated[Embedder | None, Depends(get_embedder)],
                 sessions: Annotated[Callable[[], Session], Depends(get_session_factory)],
                 idempotency_key: IdempotencyKeyHeader = None) -> dict:
    """Upload an exhibit (multipart/form-data) into a folder of the case.

    Its text is read for Case Intelligence right after the answer is sent (once per file: a file already read is not
    read again). If that doesn't happen, the next Case Intelligence request that needs it reads it.
    """
    with Audited(db, audit, user, "cm.evidence.added", "cm_case", case_id, folder=form.folder) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        file = form.file
        incoming = store.receive(file.file, get_settings().max_evidence_mb * 1024 * 1024)
        # A repeat is recognised by its form fields and the file's fingerprint.
        request = {**form.model_dump(mode="json", exclude={"file"}), "filename": file.filename, "sha256": incoming.sha256}
        once = Once(db, user, idempotency_key, f"POST /api/v1/cases/{case_id}/evidence", request)
        if (previous := once.previous()) is not None:
            store.discard(incoming)
            event.read(replayed=True)
            return previous
        meta = evidence.EvidenceMetadata(**form.model_dump(exclude={"file"}))
        added = evidence.add_evidence(db, user, family, store, incoming, filename=file.filename, declared_mime=file.content_type, meta=meta)
        seen = added.seen
        result = {"evidence": evidence_views.summaries(db, [(seen.item, seen.version)])[seen.item.id], "entry": added.entry.seq,
                  "duplicates": [evidence_views.evidence_ref(d) for d in added.duplicates]}
        once.save(status.HTTP_201_CREATED, s.EvidenceAdded, result)
        event.write(evidence=label(seen), entry=added.entry.seq, sha256=seen.obj.sha256, size_bytes=seen.version.size_bytes,
                    category=seen.item.category, classification=seen.item.classification)
    background.add_task(text_index.index_in_background, sessions, store, embedder, seen.obj.sha256, seen.item.id)
    return result


@router.post("/evidence/{evidence_id}/withdraw", response_model=s.EvidenceDetail)
def withdraw_evidence(evidence_id: uuid.UUID, body: s.RequiredReason, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Withdraw a wrong exhibit, with a reason. It leaves the case's current view and stays in the history and the chain of custody."""
    with Audited(db, audit, user, "cm.evidence.withdrawn", "cm_evidence", evidence_id) as event:
        seen = _seen(db, user, evidence_id, event)
        engine.withdraw_file(db, user, seen.family, seen.item, reason=body.reason)
        result = evidence_views.detail(db, user, seen)
        event.write(reason_given=True)
    return result


# ---------------------------------------------------------------- one exhibit


@router.get("/evidence/{evidence_id}", response_model=s.EvidenceDetail)
def evidence_detail(evidence_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.evidence.view", "cm_evidence", evidence_id) as event:
        result = evidence_views.detail(db, user, _seen(db, user, evidence_id, event))
        event.read()
    return result


@router.get("/evidence/{evidence_id}/versions", response_model=s.EvidenceVersions)
def evidence_versions(evidence_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """The original (an exhibit's only version) and the analyses, transcriptions and notes derived from it."""
    with Audited(db, audit, user, "cm.evidence.versions", "cm_evidence", evidence_id) as event:
        seen = _seen(db, user, evidence_id, event)
        derived = evidence.derived_versions(db, user, seen)
        who = queries.people(db, [seen.version.uploaded_by, *(v.author_id for v, _ in derived)])
        result = {"original": evidence_views.version_view(db, seen.version, who),
                  "derived": [{"artifact_id": a.id, "display_id": a.display_id, "title": a.title, "artifact_type": a.artifact_type,
                               "version_id": v.id, "version_number": v.version_number, "author": who.get(v.author_id),
                               "created_at": v.created_at, "change_note": v.change_note} for v, a in derived]}
        event.read(count=len(derived))
    return result


@router.get("/evidence/{evidence_id}/custody", response_model=s.CustodyView)
def evidence_custody(evidence_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.custody.read", "cm_evidence", evidence_id) as event:
        result = evidence_views.custody_view(db, _seen(db, user, evidence_id, event))
        event.read()
    return result


@router.post("/evidence/{evidence_id}/custody", response_model=s.CustodyView)
def custody_action(evidence_id: uuid.UUID, body: s.CustodyAction, user: CurrentUser, db: DbSession, audit: Audit,
                   store: Store) -> dict:
    """Transfer an exhibit, or acknowledge or decline a pending transfer."""
    with Audited(db, audit, user, CUSTODY_ACTIONS[body.action], "cm_evidence", evidence_id) as event:
        seen = _seen(db, user, evidence_id, event)
        details = {}
        if body.action == "transfer":
            recorded = custody.transfer(db, user, seen, to_user_id=body.to_user_id, to_external=body.to_external, reason=body.reason,
                                        method=body.method, authorization_ref=body.authorization_ref,
                                        receipt_reference=body.receipt_reference, occurred_at=body.occurred_at)
            details = {"to_user": body.to_user_id, "to_outside_body": recorded.to_custodian_name}
        elif body.action == "acknowledge":
            recorded, check = custody.acknowledge(db, user, seen, store, transfer_event_id=body.transfer_event_id, reason=body.reason)
            details = {"integrity": check.result}
        else:
            recorded = custody.decline(db, user, seen, transfer_event_id=body.transfer_event_id, reason=body.reason)
        result = evidence_views.custody_view(db, seen)
        event.write(custody_event=recorded.id, **details)
    return result


@router.post("/evidence/{evidence_id}/verify", response_model=s.VerificationOut)
def verify_evidence(evidence_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit, store: Store) -> dict:
    """Recompute the stored file's SHA-256 and compare it with the one recorded when it was added."""
    with Audited(db, audit, user, "cm.evidence.verified", "cm_evidence", evidence_id) as event:
        seen = _seen(db, user, evidence_id, event)
        check = evidence.verify(db, user, store, seen)
        result = {**evidence_views.check_view(check, queries.people(db, [user.id])), "evidence": evidence_views.evidence_ref(seen.item)}
        event.write(result=check.result, sha256=seen.obj.sha256)
    return result


@router.post("/evidence/{evidence_id}/download-token", response_model=s.DownloadLink)
def download_token(evidence_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.evidence.download_link", "cm_evidence", evidence_id) as event:
        seen = _seen(db, user, evidence_id, event)
        token, expires = evidence.issue_download_token(user, seen)
        event.read(expires_at=expires)
    return {"url": f"/api/v1/evidence-downloads/{token}", "expires_at": expires}


@router.get("/evidence-downloads/{token}", response_class=StreamingResponse,
            responses={200: {"content": {"application/octet-stream": {}}, "description": "the exhibit's bytes, as an attachment"}})
def download(token: Annotated[str, Path(max_length=2000)], db: DbSession, audit: Audit, store: Store) -> StreamingResponse:
    """Follow a download link. No login header: the link names its user, whose access is checked again now."""
    claims = evidence.read_download_token(token)
    user = db.get(User, uuid.UUID(claims["sub"])) if claims else None
    with Audited(db, audit, user, "cm.evidence.downloaded", "cm_evidence", claims["evi"] if claims else None) as event:
        if claims is None or user is None or not user.is_active:
            raise NotVisible()
        seen = _seen(db, user, claims["evi"], event)
        if str(seen.version.id) != claims["ver"]:
            raise NotVisible(exists=True)
        if db.scalar(select(CustodyEvent.id).where(CustodyEvent.token_id == claims["jti"])):
            raise Gone("This download link was already used. Ask for a new one: each link works once.")
        check = _intact(db, store, seen, user, IntegrityTrigger.DOWNLOAD)
        custody.record_access(db, user, seen, method="download", verification_sha256=check.computed_sha256, token_id=claims["jti"])
        key, filename, size = seen.obj.storage_key, seen.version.display_filename, seen.version.size_bytes
        event.write(sha256=seen.obj.sha256, size_bytes=size)
    return StreamingResponse(store.chunks(key), media_type="application/octet-stream",
                             headers={"Content-Disposition": _attachment(filename), "Content-Length": str(size)})


def _preview_pages(store: EvidenceStore, seen: Seen) -> tuple[list[dict], bool]:
    if seen.version.mime_type in ("application/pdf", DOCX_MIME):
        pages = [{"number": p.number, "text": p.text} for p in extract_known(store.local_path(seen.obj.storage_key), seen.version.mime_type).pages]
    else:
        pages = [{"number": None, "text": text_index.decode_text(b"".join(store.chunks(seen.obj.storage_key)))}]
    kept, total, truncated = [], 0, False
    for page in pages:
        if total + len(page["text"]) > PREVIEW_MAX_CHARS:
            kept.append({**page, "text": page["text"][:PREVIEW_MAX_CHARS - total]})
            truncated = True
            break
        kept.append(page)
        total += len(page["text"])
    return kept, truncated


@router.get("/evidence/{evidence_id}/preview", response_model=s.Preview)
def preview(evidence_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit, store: Store) -> dict:
    """A safe text view: text files, and the text of PDFs and Word files. Nothing is ever rendered or run."""
    with Audited(db, audit, user, "cm.evidence.previewed", "cm_evidence", evidence_id) as event:
        seen = _seen(db, user, evidence_id, event)
        version = seen.version
        result = {"evidence": evidence_views.evidence_ref(seen.item), "kind": "none", "pages": [], "truncated": False, "reason": None}
        if version.active_content:
            result["reason"] = ("Active content (a program, script, HTML or SVG file) is never opened by the application. "
                                "Download it and examine it in a safe environment.")
        elif version.size_bytes > PREVIEW_MAX_BYTES:
            result["reason"] = f"Larger than {PREVIEW_MAX_BYTES // (1024 * 1024)} MB: download it to view it."
        elif seen.item.category != FileCategory.TEXT and version.mime_type not in ("application/pdf", DOCX_MIME):
            result["reason"] = "No preview for this kind of file yet (images and media come with the screens): download it."
        else:
            check = _intact(db, store, seen, user, IntegrityTrigger.PREVIEW)
            try:
                result["pages"], result["truncated"] = _preview_pages(store, seen)
                result["kind"] = "text"
            except ExtractionError as exc:
                result["reason"] = str(exc)
            if result["kind"] == "text":
                custody.record_access(db, user, seen, method="preview", verification_sha256=check.computed_sha256)
        if result["kind"] == "text":
            event.write(kind="text")
        else:
            event.read(kind="none")
    return result


@router.post("/evidence/{evidence_id}/seal", response_model=s.EvidenceDetail)
def seal(evidence_id: uuid.UUID, body: s.SealChange, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Hide an exhibit from everyone but the case's supervisor and administrators. Nothing is removed."""
    with Audited(db, audit, user, "cm.evidence.sealed", "cm_evidence", evidence_id) as event:
        seen = _seen(db, user, evidence_id, event)
        evidence.set_sealed(db, user, seen, sealed=True, reason=body.reason)
        event.write()
    return evidence_views.detail(db, user, seen)


@router.post("/evidence/{evidence_id}/unseal", response_model=s.EvidenceDetail)
def unseal(evidence_id: uuid.UUID, body: s.SealChange, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.evidence.unsealed", "cm_evidence", evidence_id) as event:
        seen = _seen(db, user, evidence_id, event)
        evidence.set_sealed(db, user, seen, sealed=False, reason=body.reason)
        event.write()
    return evidence_views.detail(db, user, seen)


# ---------------------------------------------------------------- administration


@router.get("/admin/evidence-integrity", response_model=s.IntegrityReport)
def admin_evidence_integrity(user: CurrentUser, db: DbSession, audit: Audit, limit: Limit = 50, cursor: Cursor = None) -> dict:
    """Every exhibit of the organisation with its latest integrity check: failures first, then never checked."""
    with Audited(db, audit, user, "cm.admin.evidence_integrity", "cm_evidence") as event:
        _require_admin(user)
        offset = _offset(cursor)
        counts, items, total = evidence_views.integrity_report(db, user, limit=limit, offset=offset)
        event.read(**counts)
    return {"counts": counts, "items": items, "total": total, "next_cursor": _next(offset, limit, total)}
