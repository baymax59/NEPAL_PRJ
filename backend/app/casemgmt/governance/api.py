"""Reports and governance: the endpoints (phase CM-7, docs/case-management/06).

As everywhere in the module: every request is audited, anything not visible answers 404, nothing is deleted
(DELETE, PUT and PATCH answer 405), and writes go through the same rules as everything else in the case.
"""

import re
import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Path, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.auth.dependencies import CurrentUser
from app.casemgmt import queries
from app.casemgmt import schemas as s
from app.casemgmt.access import get_family, is_super_admin
from app.casemgmt.api import Audit, Audited, DbSession, IdempotencyKeyHeader
from app.casemgmt.errors import Forbidden, NotVisible
from app.casemgmt.governance import audit_chain, holds, jobs, reports, retention
from app.casemgmt.idempotency import Once
from app.casemgmt.models import AuditCheckpoint
from app.casemgmt.storage import EvidenceStore, get_evidence_store
from app.core.config import get_settings
from app.db.models import AuditEvent, User

router = APIRouter(prefix="/v1", tags=["case management: reports and governance"])
Store = Annotated[EvidenceStore, Depends(get_evidence_store)]


def _require_admin(user: User) -> None:
    if not is_super_admin(user):
        raise Forbidden("Only platform administrators can use the governance views")


# ---------------------------------------------------------------- signed PDF reports


@router.post("/cases/{case_id}/reports", response_model=s.ReportGenerated, status_code=status.HTTP_201_CREATED)
def generate_report(case_id: uuid.UUID, body: s.ReportCreate, user: CurrentUser, db: DbSession, audit: Audit, store: Store,
                    idempotency_key: IdempotencyKeyHeader = None):
    """A PDF report of the case as it stands, kept write-once and added to the case as a new report version."""
    with Audited(db, audit, user, "cm.report.generated", "cm_case", case_id, report_type=body.report_type) as event:
        once = Once(db, user, idempotency_key, f"POST /api/v1/cases/{case_id}/reports", body.model_dump(mode="json"))
        if (previous := once.previous()) is not None:
            event.read(replayed=True)
            return previous
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        made = reports.generate(db, user, family, store, report_type=body.report_type, purpose=body.purpose)
        result = {"entry": made["entry"].seq, "report": reports.export_view(db, made["export"])}
        once.save(status.HTTP_201_CREATED, s.ReportGenerated, result)
        event.write(report=made["artifact"].display_id, version=made["version"].version_number, sha256=made["export"].sha256,
                    as_of_entry=made["export"].subject_entry_seq, pages=made["export"].page_count,
                    withheld=made["export"].withheld_entries)
    return result


@router.get("/cases/{case_id}/reports", response_model=s.ReportsView)
def list_reports(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """The report versions of the case."""
    with Audited(db, audit, user, "cm.report.list", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        result = reports.reports_of(db, user, family)
        event.read(reports=len(result["reports"]))
    return result


@router.get("/reports/{export_id}", response_model=s.ReportDetail)
def report_detail(export_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.report.viewed", "cm_report", export_id) as event:
        export = reports.visible_export(db, user, export_id)
        checks = reports._checks(db, [export.id])
        result = {**reports.export_view(db, export, last_check=checks.get(export.id)), "history": reports.check_history(db, export)}
        event.read(sha256=export.sha256)
    return result


@router.post("/reports/{export_id}/download-link", response_model=s.DownloadLink)
def report_download_link(export_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.report.download_link", "cm_report", export_id) as event:
        export = reports.visible_export(db, user, export_id)
        token, expires = reports.issue_download_token(user, export)
        event.read(expires_at=expires.isoformat())
    return {"url": f"/api/v1/report-downloads/{token}", "expires_at": expires}


def _attachment(filename: str) -> str:
    plain = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "report.pdf"
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(filename)}"


@router.get("/report-downloads/{token}", response_class=StreamingResponse,
            responses={200: {"content": {"application/pdf": {}}, "description": "the report's PDF, as an attachment"}})
def report_download(token: Annotated[str, Path(max_length=2000)], db: DbSession, audit: Audit, store: Store) -> StreamingResponse:
    """Follow a one-time link. The stored copy is checked against its recorded hash before it is sent."""
    claims = reports.read_download_token(token)
    user = db.get(User, uuid.UUID(claims["sub"])) if claims else None
    with Audited(db, audit, user, "cm.report.downloaded", "cm_report", claims["rep"] if claims else None) as event:
        if claims is None or user is None or not user.is_active:
            raise NotVisible()
        export = reports.prepare_download(db, store, user, claims)
        file_name = reports.export_view(db, export)["file_name"] or "report.pdf"
        key, size = export.storage_key, export.size_bytes
        event.write(sha256=export.sha256, size_bytes=size)
    return StreamingResponse(store.chunks(key), media_type="application/pdf",
                             headers={"Content-Disposition": _attachment(file_name), "Content-Length": str(size)})


def _check_result(db, user: User, check, export, may_see: bool) -> dict:
    if check.result == "match":
        message = "This file is exactly the report Knight Hawk generated: not one byte has changed."
    elif check.result == "mismatch":
        message = "The stored copy no longer matches the fingerprint recorded when the report was generated: it was changed."
    elif check.result == "missing":
        message = "The stored copy of the report is missing."
    else:
        message = ("No report generated by Knight Hawk in your organisation has exactly this content. It may have been changed, "
                   "or it is not a Knight Hawk report.")
    if check.result == "match" and export is not None and not may_see:
        message += " You don't have access to its case, so its details aren't shown."
    return {"result": check.result, "method": check.method, "computed_sha256": check.computed_sha256,
            "recorded_sha256": export.sha256 if export is not None and may_see else None, "checked_at": check.checked_at,
            "report": reports.export_view(db, export, last_check=check, who=None) if export is not None and may_see else None,
            "message": message}


@router.post("/reports/{export_id}/verify", response_model=s.ReportCheck)
def verify_report(export_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit, store: Store) -> dict:
    """Hash the stored copy again and compare it with the hash recorded when the report was generated."""
    with Audited(db, audit, user, "cm.report.verified", "cm_report", export_id) as event:
        export = reports.visible_export(db, user, export_id)
        check = reports.check_stored(db, store, user, export)
        result = _check_result(db, user, check, export, True)
        event.write(result=check.result, method=check.method)
    return result


@router.post("/reports/verify-file", response_model=s.ReportCheck)
def verify_report_file(user: CurrentUser, db: DbSession, audit: Audit, file: Annotated[UploadFile, File(description="The PDF to check")]) -> dict:
    """Check a copy someone holds (printed from a download, e-mailed): is it byte for byte a report Knight Hawk generated?
    The file is only hashed, never kept."""
    with Audited(db, audit, user, "cm.report.verified", "cm_report") as event:
        sha256 = reports.hash_upload(file.file)
        check, export, may_see = reports.check_submitted(db, user, sha256)
        if export is not None:
            event.target_id = export.id
        result = _check_result(db, user, check, export, may_see)
        event.write(result=check.result, method=check.method, sha256=sha256)
    return result


# ---------------------------------------------------------------- legal holds and retention of one case


@router.get("/cases/{case_id}/governance", response_model=s.CaseGovernance)
def case_governance(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """The case's legal holds, retention decisions and review date."""
    with Audited(db, audit, user, "cm.governance.case_read", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        result = retention.for_case(db, user, family)
        event.read(on_hold=result["on_hold"], decisions=len(result["decisions"]))
    return result


@router.post("/cases/{case_id}/legal-holds", response_model=s.LegalHoldOut, status_code=status.HTTP_201_CREATED)
def place_hold(case_id: uuid.UUID, body: s.LegalHoldCreate, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Place a legal hold: the case can't be archived, nor a retention decision approved, until it is released."""
    with Audited(db, audit, user, "cm.legal_hold.placed", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        hold = holds.place(db, user, family, reason=body.reason, authority_ref=body.authority_ref)
        result = holds.view(hold, queries.people(db, [hold.placed_by]))
        event.write(hold=str(hold.id), authority_ref=bool(hold.authority_ref))
    return result


@router.post("/legal-holds/{hold_id}/release", response_model=s.LegalHoldOut)
def release_hold(hold_id: uuid.UUID, body: s.RequiredNote, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.legal_hold.released", "cm_legal_hold", hold_id) as event:
        hold, family = holds.get_hold(db, user, hold_id)
        event.target_id = family.display_id
        holds.release(db, user, hold, family, reason=body.reason)
        result = holds.view(hold, queries.people(db, [hold.placed_by, hold.released_by]))
        event.write(hold=str(hold.id))
    return result


@router.post("/cases/{case_id}/retention-decisions", response_model=s.RetentionDecisionOut, status_code=status.HTTP_201_CREATED)
def propose_retention(case_id: uuid.UUID, body: s.RetentionDecisionCreate, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Propose a retention decision about a case; a different person decides it."""
    with Audited(db, audit, user, "cm.retention.proposed", "cm_case", case_id, retention_action=body.action) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        decision = retention.propose(db, user, family, action=body.action, reason=body.reason, policy_id=body.policy_id,
                                     review_on=body.review_on, transfer_to=body.transfer_to)
        result = retention.decision_view(decision, queries.people(db, [decision.proposed_by]), {})
        event.write(decision=str(decision.id))
    return result


@router.post("/retention-decisions/{decision_id}/decide", response_model=s.RetentionDecisionOut)
def decide_retention(decision_id: uuid.UUID, body: s.RetentionDecide, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.retention.decided", "cm_retention_decision", decision_id, approve=body.approve) as event:
        decision, family = retention.get_decision(db, user, decision_id)
        event.target_id = family.display_id
        retention.decide(db, user, decision, family, approve=body.approve, note=body.note)
        result = retention.decision_view(decision, queries.people(db, [decision.proposed_by, decision.decided_by]), {})
        event.write(decision=str(decision.id), retention_action=decision.action, status=decision.status)
    return result


@router.post("/retention-decisions/{decision_id}/withdraw", response_model=s.RetentionDecisionOut)
def withdraw_retention(decision_id: uuid.UUID, body: s.RequiredNote, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.retention.withdrawn", "cm_retention_decision", decision_id) as event:
        decision, family = retention.get_decision(db, user, decision_id)
        event.target_id = family.display_id
        retention.withdraw(db, user, decision, family, reason=body.reason)
        result = retention.decision_view(decision, queries.people(db, [decision.proposed_by]), {})
        event.write(decision=str(decision.id))
    return result


# ---------------------------------------------------------------- administration: retention, audit chain, jobs


@router.get("/admin/retention", response_model=s.RetentionOverview)
def retention_overview(user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.retention.overview", "cm_retention") as event:
        result = retention.overview(db, user)
        event.read(due=len(result["due"]), waiting=len(result["waiting"]))
    return result


@router.post("/admin/retention/policies", response_model=s.RetentionPolicyOut, status_code=status.HTTP_201_CREATED)
def create_retention_policy(body: s.RetentionPolicyCreate, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.retention.policy_created", "cm_retention_policy", body.code) as event:
        policy = retention.create_policy(db, user, **body.model_dump())
        result = retention.policy_view(policy, queries.people(db, [policy.created_by]))
        event.write(policy=policy.code, years=policy.review_after_years)
    return result


@router.post("/admin/retention/policies/{policy_id}/retire", response_model=s.RetentionPolicyOut)
def retire_retention_policy(policy_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.retention.policy_retired", "cm_retention_policy", policy_id) as event:
        policy = retention.retire_policy(db, user, policy_id)
        event.target_id = policy.code
        result = retention.policy_view(policy, queries.people(db, [policy.created_by]))
        event.write()
    return result


@router.get("/admin/governance", response_model=s.GovernanceOverview)
def governance_overview(user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """The audit chain, its checkpoints, the scheduled jobs, the active legal holds and the security settings."""
    with Audited(db, audit, user, "cm.governance.overview", "cm_governance") as event:
        _require_admin(user)
        settings = get_settings()
        last = audit_chain.latest(db)
        checkpoints = list(db.scalars(select(AuditCheckpoint).order_by(AuditCheckpoint.chain_seq.desc()).limit(20)))
        events = db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.chain_seq.is_not(None))) or 0
        who = queries.people(db, [c.created_by for c in checkpoints])
        result = {
            "chain": {"events": events, "last_seq": last[0] if last else None, "last_hash": last[1] if last else None,
                      "since_last_checkpoint": (last[0] - (checkpoints[0].chain_seq if checkpoints else 0)) if last else 0,
                      "key_id": audit_chain.key_id(audit_chain.checkpoint_key())},
            "checkpoints": [audit_chain.checkpoint_view(c, who) for c in checkpoints],
            "jobs": jobs.overview(db),
            "legal_holds": holds.all_active(db, user),
            "settings": {"mfa_required": settings.cm_mfa_required, "checkpoint_key_set": settings.cm_checkpoint_key is not None,
                         "mfa_key_set": settings.mfa_key is not None,
                         "runtime_login": bool(settings.postgres_app_user and settings.postgres_app_password is not None),
                         "test_source": settings.cm_test_source},
        }
        event.read(events=events)
    return result


def _run_job(name: str, user: User, db, audit, store: EvidenceStore, action: str) -> dict:
    with Audited(db, audit, user, action, "cm_job", name) as event:
        _require_admin(user)
        if name == "audit_checkpoint":
            from app.auth.mfa import require_strong_auth
            require_strong_auth(user, "signing the audit chain")
        run = jobs.run(db, store, name, user)
        result = jobs.run_view(run, queries.people(db, [user.id]))
        event.write(status=run.status, run=run.id)
    return result


@router.post("/admin/audit/verify", response_model=s.JobRunOut)
def verify_audit_chain(user: CurrentUser, db: DbSession, audit: Audit, store: Store) -> dict:
    """Recompute the whole audit chain and check every signed checkpoint, now. The result is recorded as a job run."""
    return _run_job("audit_verify", user, db, audit, store, "cm.audit.verified")


@router.post("/admin/audit/checkpoints", response_model=s.JobRunOut)
def create_audit_checkpoint(user: CurrentUser, db: DbSession, audit: Audit, store: Store) -> dict:
    """Sign the audit chain as it stands now (a checkpoint), and keep the signed record in the write-once store."""
    return _run_job("audit_checkpoint", user, db, audit, store, "cm.audit.checkpoint")


@router.post("/admin/jobs/{job}/run", response_model=s.JobRunOut)
def run_job(job: Annotated[str, Path(pattern=r"^(audit_checkpoint|audit_verify|evidence_sweep)$")], user: CurrentUser, db: DbSession,
            audit: Audit, store: Store) -> dict:
    """Run one of the scheduled jobs now (it is recorded like the worker's runs)."""
    return _run_job(job, user, db, audit, store, "cm.governance.job_started")
