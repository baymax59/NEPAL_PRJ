"""Signed PDF reports (phase CM-7, docs/case-management/03 §5 "Report").

A report is generated from the case as it stands (as of its latest history entry) and becomes part of the case:
1. It contains what **every member of the case** may see (report.report_preview, shared view): anyone
   who can open the case can read the report, so nothing sealed or classified above the case goes into it.
2. The PDF is built (pdf.py) and kept in the write-once store under its SHA-256.
3. A new version of the report note (in the case's "reports" folder, e.g. RPT-0001 v2) is added, with the file's hash in its
   content, and an entry of the case's history says which entry the report describes: the history chain itself vouches
   for the file. The export is recorded (report_exports) and audited by the API.
4. A copy can be checked at any time: the stored copy is hashed again, and a copy someone holds (printed, e-mailed)
   can be uploaded and compared. A changed file fails the check. Downloads use one-time links and are recorded.

No report is represented as automatically admissible in court (report.DISCLAIMER is printed in every one).
"""

import datetime as dt
import hashlib
import hmac
import io
import uuid
from typing import BinaryIO

import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.casemgmt import engine, history, queries, report
from app.casemgmt.access import case_condition, require, rights, supervises
from app.casemgmt.enums import (
    ArtifactType,
    FileStatus,
    HistoryKind,
    ReportCheckMethod,
    ReportCheckResult,
    ReportType,
)
from app.casemgmt.errors import Conflict, Gone, Invalid, NotVisible, TooLarge
from app.casemgmt.governance import pdf
from app.casemgmt.intelligence.timeline import TIMELINE_TITLE
from app.casemgmt.models import (
    Artifact,
    ArtifactVersion,
    CaseFamily,
    CustodyEvent,
    ReportDownload,
    ReportExport,
    ReportVerification,
)
from app.casemgmt.storage import EvidenceStore
from app.core.config import get_settings
from app.db.models import User

TITLES = {ReportType.CASE_REPORT: "Case report", ReportType.EVIDENCE_REGISTER: "Evidence register"}
FOLDER = "reports"
MAX_REPORT_BYTES = 200 * 1024 * 1024
MAX_CHECKED_UPLOAD = 200 * 1024 * 1024
TIMELINE_ENTRIES = 150
LINK_PURPOSE = "report-download"
CUSTODY_LABELS = {
    "collected": "Collected", "ingested": "Received into the evidence store", "transferred": "Handed over",
    "acknowledged": "Receipt acknowledged", "declined": "Handover declined", "accessed": "Accessed", "verified": "Integrity verified",
    "sealed": "Sealed", "unsealed": "Unsealed", "exported": "Exported",
}


def _kind(value: str) -> ReportType:
    try:
        return ReportType(value)
    except ValueError:
        raise Invalid(f"Unknown kind of report: use one of {', '.join(t.value for t in ReportType)}") from None


def _report_artifact(session: Session, family: CaseFamily, kind: ReportType) -> Artifact | None:
    """The case's report note of this kind (its versions are the successive reports), if one was made already."""
    return session.scalar(select(Artifact).where(Artifact.case_family_id == family.id, Artifact.artifact_type == ArtifactType.REPORT.value,
                                                 Artifact.title == f"{TITLES[kind]} ({family.display_id})"))


def _next_id(session: Session, family: CaseFamily, artifact: Artifact | None) -> tuple[str, int]:
    """The report's display ID and version number, exactly as engine._new_version will assign them (the case is locked)."""
    if artifact is not None:
        last = session.scalar(select(func.max(ArtifactVersion.version_number)).where(ArtifactVersion.artifact_id == artifact.id))
        return artifact.display_id, last + 1
    count = session.scalar(select(func.count()).select_from(Artifact).where(Artifact.case_family_id == family.id,
                                                                             Artifact.display_id.like("RPT-%")))
    return f"RPT-{count + 1:04d}", 1


def _person(person: dict | None) -> str:
    return f"{person['display_name']} (@{person['username']})" if person else "—"


def _custodian(value: dict | None) -> str:
    if not value:
        return "—"
    return value["user"]["display_name"] if value.get("user") else (value.get("name") or "—")


def _timeline(session: Session, family: CaseFamily) -> list[dict]:
    """The reconstructed timeline as it stands, if there is one that every member may see."""
    artifact = session.scalar(select(Artifact).where(
        Artifact.case_family_id == family.id, Artifact.artifact_type == ArtifactType.TIMELINE.value, Artifact.title == TIMELINE_TITLE,
        Artifact.status == FileStatus.ACTIVE.value))
    if artifact is None or artifact.sealed:
        return []
    content = engine.latest_version(session, artifact).content or {}
    rows = []
    for event in content.get("events", [])[:TIMELINE_ENTRIES]:
        source = event.get("source") or {}
        page = f", p.{event['page']}" if event.get("page") else ""
        rows.append({"date": event.get("date") or "", "description": event.get("description") or "",
                     "source": f"{source.get('display_id') or '—'}{page}"})
    return rows


def _custody(session: Session, evidence_rows: list[dict]) -> dict[str, list[dict]]:
    """Each listed exhibit's chain of custody, oldest first."""
    ids = {uuid.UUID(str(e["item_id"])): e["display_id"] for e in evidence_rows}
    if not ids:
        return {}
    events = list(session.scalars(select(CustodyEvent).where(CustodyEvent.evidence_item_id.in_(list(ids)))
                                  .order_by(CustodyEvent.evidence_item_id, CustodyEvent.id)))
    who = queries.people(session, [e.actor_id for e in events] + [e.from_custodian_id for e in events] + [e.to_custodian_id for e in events])
    found: dict[str, list[dict]] = {}
    for e in events:
        source = who.get(e.from_custodian_id, {}).get("display_name") if e.from_custodian_id else e.from_custodian_name
        target = who.get(e.to_custodian_id, {}).get("display_name") if e.to_custodian_id else e.to_custodian_name
        parties = " → ".join(p for p in (source, target) if p) or "—"
        method = "automatic file check" if e.method == "sha256" else e.method  # the stored name is kept; people read words
        details = "; ".join(x for x in (e.reason, method, e.authorization_ref,
                                        "file checked at this moment" if e.verification_sha256 else None) if x)
        found.setdefault(ids[e.evidence_item_id], []).append({
            "occurred_at": e.occurred_at, "label": CUSTODY_LABELS.get(e.event_type, e.event_type), "parties": parties,
            "actor": who.get(e.actor_id, {}).get("display_name", "—"), "details": details or "—"})
    return found


def generate(session: Session, actor: User, family: CaseFamily, store: EvidenceStore, *, report_type: str, purpose: str) -> dict:
    """Build the PDF from the case as it stands, keep it, and add it to the case as a new report version."""
    family = engine._lock_family(session, family.id)
    found = rights(session, actor, family)
    require(found.add_files, "You can read this case but not add to it", found)
    kind = _kind(report_type)
    purpose = (purpose or "").strip()
    if not 10 <= len(purpose) <= 500:
        raise Invalid("Say what the report is for (10 to 500 characters): it is printed in the report")
    artifact = _report_artifact(session, family, kind)
    display_id, number = _next_id(session, family, artifact)
    as_of = history.last_entry(session, family.id).seq

    preview = report.report_preview(session, actor, family, shared=True)
    generated_at = dt.datetime.now(dt.UTC)
    info = pdf.ReportInfo(display_id=display_id, version=number, report_type=kind.value, title=f"{TITLES[kind]} of {family.display_id}",
                          purpose=purpose, generated_at=generated_at, generated_by=f"{actor.display_name} (@{actor.username})",
                          case=family.display_id, as_of_entry=as_of, classification=family.classification,
                          timeline=_timeline(session, family) if kind == ReportType.CASE_REPORT else [],
                          custody=_custody(session, preview["evidence"]) if kind == ReportType.EVIDENCE_REGISTER else {})
    for row in preview["evidence"]:
        row["custodian"] = {"name": _custodian(row.get("custodian")), "user": None}
    data, pages = pdf.build(preview, info)
    if len(data) > MAX_REPORT_BYTES:
        raise TooLarge("The report is larger than 200 MB: generate an evidence register, or split the case")
    incoming = store.receive(io.BytesIO(data), MAX_REPORT_BYTES)
    storage_key, _ = store.keep(incoming)

    file_name = f"{family.display_id}-{display_id}-v{number}.pdf"
    content = {"report_type": kind.value, "title": TITLES[kind], "purpose": purpose, "as_of_entry": as_of, "file_name": file_name,
               "sha256": incoming.sha256, "size_bytes": incoming.size, "pages": pages, "withheld_entries": preview["withheld_entries"],
               "generated_at": generated_at.isoformat(), "disclaimer": report.DISCLAIMER}
    previous = engine.latest_version(session, artifact) if artifact else None
    folder = engine.ensure_folder(session, family, actor, FOLDER, system=True)
    artifact, version = engine._new_version(session, family=family, folder=folder, artifact=artifact, artifact_type=ArtifactType.REPORT,
                                            title=f"{TITLES[kind]} ({family.display_id})", content=content, author=actor,
                                            change_note=f"Generated from the case as it stood: {purpose[:200]}",
                                            derived_from=[str(previous.id)] if previous else [])
    if (artifact.display_id, version.version_number) != (display_id, number):  # the case is locked: this can't differ
        raise Conflict("The report's number changed while it was being generated. Nothing was saved: try again.")
    entry = history.append(session, family, actor, HistoryKind.REPORT_GENERATED,
                           f"{TITLES[kind]} {display_id} version {number} generated, describing the case as of entry {as_of}",
                           subject_type="artifact", subject_id=artifact.id,
                           details={"display_id": display_id, "version": number, "report_type": kind.value, "as_of_entry": as_of,
                                    "sha256": incoming.sha256})
    export = ReportExport(organization_id=family.organization_id, case_family_id=family.id, subject_entry_seq=as_of,
                          artifact_id=artifact.id, artifact_version_id=version.id, report_type=kind.value, purpose=purpose,
                          file_format="pdf", sha256=incoming.sha256, size_bytes=incoming.size, page_count=pages,
                          storage_backend=store.backend, storage_key=storage_key, withheld_entries=preview["withheld_entries"],
                          generated_by=actor.id, generated_at=generated_at)
    session.add(export)
    session.flush()
    return {"export": export, "entry": entry, "artifact": artifact, "version": version}


# ---------------------------------------------------------------- reading


def visible_export(session: Session, user: User, export_id) -> ReportExport:
    """A report version the user may see: its case open to them, and not sealed (unless they supervise the case). 404 otherwise."""
    export = session.get(ReportExport, export_id)
    if export is None:
        raise NotVisible()
    family = session.scalar(select(CaseFamily).where(CaseFamily.id == export.case_family_id, case_condition(user)))
    artifact = session.get(Artifact, export.artifact_id)
    if family is None or (artifact.sealed and not supervises(user, family)):
        raise NotVisible(exists=True)
    return export


def _checks(session: Session, export_ids) -> dict:
    latest: dict = {}
    for check in session.scalars(select(ReportVerification).where(ReportVerification.report_export_id.in_(list(export_ids)))
                                 .order_by(ReportVerification.id)):
        latest[check.report_export_id] = check
    return latest


def check_view(check: ReportVerification | None, who: dict) -> dict | None:
    if check is None:
        return None
    return {"result": check.result, "method": check.method, "computed_sha256": check.computed_sha256,
            "checked_at": check.checked_at, "checked_by": who.get(check.checked_by)}


def export_view(session: Session, export: ReportExport, *, last_check: ReportVerification | None = None, who: dict | None = None) -> dict:
    version = session.get(ArtifactVersion, export.artifact_version_id)
    artifact = session.get(Artifact, export.artifact_id)
    who = who if who is not None else queries.people(session, [export.generated_by] + ([last_check.checked_by] if last_check else []))
    content = version.content or {}
    return {"id": export.id, "display_id": artifact.display_id, "version_number": version.version_number, "report_type": export.report_type,
            "title": content.get("title") or artifact.title, "purpose": export.purpose, "file_name": content.get("file_name"),
            "sha256": export.sha256, "size_bytes": export.size_bytes, "page_count": export.page_count,
            "as_of_entry": export.subject_entry_seq, "case_id": export.case_family_id,
            "withheld_entries": export.withheld_entries, "generated_by": who.get(export.generated_by), "generated_at": export.generated_at,
            "sealed": artifact.sealed, "last_check": check_view(last_check, who)}


def reports_of(session: Session, viewer: User, family: CaseFamily) -> dict:
    """The report versions of the case that the viewer may see, newest first."""
    exports = list(session.scalars(select(ReportExport).where(ReportExport.case_family_id == family.id)
                                   .order_by(ReportExport.generated_at.desc(), ReportExport.id.desc())))
    sealed = set() if supervises(viewer, family) else set(session.scalars(
        select(Artifact.id).where(Artifact.case_family_id == family.id, Artifact.sealed.is_(True))))
    shown = [e for e in exports if e.artifact_id not in sealed]
    checks = _checks(session, [e.id for e in shown])
    who = queries.people(session, [e.generated_by for e in shown] + [c.checked_by for c in checks.values()])
    return {"case": queries.case_ref(family), "entries": history.last_entry(session, family.id).seq,
            "reports": [export_view(session, e, last_check=checks.get(e.id), who=who) for e in shown],
            "report_types": [{"code": t.value, "label": label} for t, label in TITLES.items()]}


def check_history(session: Session, export: ReportExport) -> list[dict]:
    checks = list(session.scalars(select(ReportVerification).where(ReportVerification.report_export_id == export.id)
                                  .order_by(ReportVerification.id.desc()).limit(50)))
    downloads = list(session.scalars(select(ReportDownload).where(ReportDownload.report_export_id == export.id)
                                     .order_by(ReportDownload.id.desc()).limit(50)))
    who = queries.people(session, [c.checked_by for c in checks] + [d.downloaded_by for d in downloads])
    return ([{"kind": "check", "at": c.checked_at, "by": who.get(c.checked_by), "result": c.result, "method": c.method} for c in checks]
            + [{"kind": "download", "at": d.downloaded_at, "by": who.get(d.downloaded_by), "result": None, "method": None} for d in downloads])


# ---------------------------------------------------------------- checking a report


def check_stored(session: Session, store: EvidenceStore, user: User | None, export: ReportExport) -> ReportVerification:
    """Hash the stored copy again and compare it with the hash recorded when the report was generated."""
    computed = store.hash(export.storage_key)
    if computed is None:
        result = ReportCheckResult.MISSING
    else:
        result = ReportCheckResult.MATCH if hmac.compare_digest(computed, export.sha256) else ReportCheckResult.MISMATCH
    check = ReportVerification(report_export_id=export.id, method=ReportCheckMethod.STORED_COPY.value, result=result.value,
                               computed_sha256=computed, checked_by=user.id if user else None)
    session.add(check)
    session.flush()
    return check


def hash_upload(stream: BinaryIO) -> str:
    digest, size = hashlib.sha256(), 0
    while block := stream.read(1024 * 1024):
        size += len(block)
        if size > MAX_CHECKED_UPLOAD:
            raise TooLarge("The file is larger than 200 MB: no Knight Hawk report is that large")
        digest.update(block)
    if size == 0:
        raise Invalid("The file is empty")
    return digest.hexdigest()


def check_submitted(session: Session, user: User, sha256: str) -> tuple[ReportVerification, ReportExport | None, bool]:
    """A copy someone holds: is it, byte for byte, a report generated by Knight Hawk in the user's organisation?
    Returns (the recorded check, the report or None, whether the user may see that report). The file isn't kept."""
    export = session.scalar(select(ReportExport).where(ReportExport.sha256 == sha256, ReportExport.organization_id == user.organization_id)
                            .order_by(ReportExport.generated_at).limit(1)) if user.organization_id else None
    result = ReportCheckResult.MATCH if export else ReportCheckResult.UNKNOWN
    check = ReportVerification(report_export_id=export.id if export else None, method=ReportCheckMethod.SUBMITTED_COPY.value,
                               result=result.value, computed_sha256=sha256, checked_by=user.id)
    session.add(check)
    session.flush()
    may_see = False
    if export is not None:
        try:
            visible_export(session, user, export.id)
            may_see = True
        except NotVisible:
            may_see = False
    return check, export, may_see


# ---------------------------------------------------------------- one-time download links


def _token_key() -> bytes:
    secret = get_settings().jwt_secret.get_secret_value().encode()
    return hmac.new(secret, b"case-management report download v1", hashlib.sha256).digest()


def issue_download_token(user: User, export: ReportExport) -> tuple[str, dt.datetime]:
    now = dt.datetime.now(dt.UTC)
    expires = now + dt.timedelta(minutes=get_settings().evidence_download_minutes)
    claims = {"sub": str(user.id), "rep": str(export.id), "iat": now, "exp": expires, "jti": uuid.uuid4().hex, "purpose": LINK_PURPOSE}
    return jwt.encode(claims, _token_key(), algorithm="HS256"), expires


def read_download_token(token: str) -> dict | None:
    try:
        claims = jwt.decode(token, _token_key(), algorithms=["HS256"], options={"require": ["exp", "iat", "sub", "jti"]})
        uuid.UUID(claims["sub"])
        uuid.UUID(claims["rep"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None
    return claims if claims.get("purpose") == LINK_PURPOSE else None


def prepare_download(session: Session, store: EvidenceStore, user: User, claims: dict) -> ReportExport:
    """Check the link, the user's access (again, now) and the stored copy; record the download. The caller sends the file."""
    export = visible_export(session, user, claims["rep"])
    if session.scalar(select(ReportDownload.id).where(ReportDownload.token_id == claims["jti"])):
        raise Gone("This download link was already used. Ask for a new one: each link works once.")
    check = check_stored(session, store, user, export)
    if check.result != ReportCheckResult.MATCH.value:
        session.commit()  # the failed check stays on record although the request is refused
        raise Conflict("The stored copy of this report no longer matches the fingerprint recorded when it was generated. "
                       "It was not sent: an administrator must check the evidence store.", check=check.result)
    session.add(ReportDownload(report_export_id=export.id, token_id=claims["jti"], downloaded_by=user.id, verified_sha256=check.computed_sha256))
    session.flush()
    return export
