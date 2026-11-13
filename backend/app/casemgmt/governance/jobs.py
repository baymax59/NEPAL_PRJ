"""Scheduled jobs (phase CM-7), run by the worker (scripts/worker.py) when they are due:

- audit_checkpoint: signs the audit chain every 24 hours, or sooner once 1,000 events were added since the last one.
- audit_verify: every 24 hours, recomputes the whole chain and checks every checkpoint. If anything is broken, the
  run fails and every platform administrator gets a notice.
- evidence_sweep: every 24 hours, hashes every stored evidence file again (what scripts.verify_evidence does). A
  changed or missing file: a warning, and a notice to the administrators.

Every run is recorded (job_runs) and audited. Administrators can start a job by hand; that run is recorded the same way.
Why a small worker and not Valkey + RQ (planned in docs/case-management/08, decision 4): the jobs are few and daily,
a table in PostgreSQL records them, and one service less has to be run and secured. See decision 10 there.
"""

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.log import AuditLog
from app.casemgmt import evidence, queries
from app.casemgmt.enums import CheckpointReason, IntegrityResult, JobStatus, OrgRole
from app.casemgmt.governance import audit_chain
from app.casemgmt.models import AuditCheckpoint, JobRun
from app.casemgmt.notifications import notify
from app.casemgmt.storage import EvidenceStore
from app.core.enums import AuditOutcome
from app.db.models import User

DAY = dt.timedelta(hours=24)
CHECKPOINT_AFTER_EVENTS = 1000


@dataclass(frozen=True)
class Job:
    name: str
    label: str
    every: dt.timedelta
    run: Callable[[Session, EvidenceStore, User | None], tuple[JobStatus, dict]]


def _admins(session: Session) -> list:
    return list(session.scalars(select(User.id).where(User.org_role == OrgRole.SUPER_ADMIN.value, User.is_active.is_(True))))


def _last_checkpoint_seq(session: Session) -> int:
    return session.scalar(select(func.max(AuditCheckpoint.chain_seq))) or 0


def _checkpoint(session: Session, store: EvidenceStore, actor: User | None) -> tuple[JobStatus, dict]:
    last = audit_chain.latest(session)
    if last is None:
        return JobStatus.OK, {"signed": False, "why": "no Case Management event yet"}
    if last[0] == _last_checkpoint_seq(session):
        return JobStatus.OK, {"signed": False, "why": f"nothing new since the checkpoint at event {last[0]}"}
    reason = CheckpointReason.MANUAL if actor else CheckpointReason.SCHEDULED
    checkpoint = audit_chain.create_checkpoint(session, store, actor, reason)
    return JobStatus.OK, {"signed": True, "chain_seq": checkpoint.chain_seq, "key_id": checkpoint.key_id}


def _verify(session: Session, store: EvidenceStore, actor: User | None) -> tuple[JobStatus, dict]:
    report = audit_chain.verify(session, store)
    if not report.intact:
        notify(session, _admins(session), "governance.audit_chain_broken", actor=actor,
               problems=len(report.breaks) + report.more_breaks, first_event=report.breaks[0].chain_seq)
    return (JobStatus.OK if report.intact else JobStatus.FAILED), report.as_dict()


def _sweep(session: Session, store: EvidenceStore, actor: User | None) -> tuple[JobStatus, dict]:
    checks = evidence.sweep(session, store, actor)
    counts = {result.value: sum(1 for c in checks if c.result == result.value) for result in IntegrityResult}
    bad = counts[IntegrityResult.MISMATCH.value] + counts[IntegrityResult.MISSING.value]
    if bad:
        notify(session, _admins(session), "governance.evidence_integrity", actor=actor, changed=counts[IntegrityResult.MISMATCH.value],
               missing=counts[IntegrityResult.MISSING.value])
    return (JobStatus.WARNING if bad else JobStatus.OK), {"checked": len(checks), **counts}


JOBS = {
    "audit_checkpoint": Job("audit_checkpoint", "Sign the audit chain (checkpoint)", DAY, _checkpoint),
    "audit_verify": Job("audit_verify", "Verify the audit chain and its checkpoints", DAY, _verify),
    "evidence_sweep": Job("evidence_sweep", "Check every stored evidence file", DAY, _sweep),
}


def last_runs(session: Session) -> dict[str, JobRun]:
    found: dict[str, JobRun] = {}
    for run in session.scalars(select(JobRun).order_by(JobRun.started_at)):
        found[run.job] = run
    return found


def due(session: Session, now: dt.datetime | None = None) -> list[str]:
    now = now or dt.datetime.now(dt.UTC)
    runs = last_runs(session)
    names = [name for name, job in JOBS.items() if name not in runs or now - runs[name].started_at >= job.every]
    if "audit_checkpoint" not in names:
        last = audit_chain.latest(session)
        if last and last[0] - _last_checkpoint_seq(session) >= CHECKPOINT_AFTER_EVENTS:
            names.insert(0, "audit_checkpoint")
    return names


def run(session: Session, store: EvidenceStore, name: str, actor: User | None = None, audit: AuditLog | None = None) -> JobRun:
    """Run one job now and record the run (the caller commits). A job that fails is recorded as failed, not raised."""
    job = JOBS[name]
    started = dt.datetime.now(dt.UTC)
    try:
        with session.begin_nested():
            status, summary = job.run(session, store, actor)
    except Exception as error:  # recorded, so an administrator sees it; the worker keeps running
        status, summary = JobStatus.FAILED, {"error": type(error).__name__, "message": str(error)[:500]}
    record = JobRun(job=name, started_at=started, status=status.value, summary=jsonable_encoder(summary), started_by=actor.id if actor else None)
    session.add(record)
    session.flush()
    log = audit or AuditLog(client_ip="worker", session=session)
    log.record("cm.governance.job", AuditOutcome.SUCCESS if status != JobStatus.FAILED else AuditOutcome.ERROR, user=actor,
               target_type="cm_job", target_id=name, details={"status": status.value, "run": record.id})
    return record


def run_due(sessions, store: EvidenceStore, now: dt.datetime | None = None) -> list[JobRun]:
    """Every job that is due, each in its own transaction."""
    with sessions() as session:
        names = due(session, now)
    done = []
    for name in names:
        with sessions() as session:
            done.append(run(session, store, name))
            session.commit()
    return done


def run_view(run: JobRun, who: dict) -> dict:
    job = JOBS.get(run.job)
    return {"id": run.id, "job": run.job, "label": job.label if job else run.job, "status": run.status, "started_at": run.started_at,
            "finished_at": run.finished_at, "summary": run.summary, "started_by": who.get(run.started_by)}


def overview(session: Session) -> list[dict]:
    """Each job, its last run and when it is next due."""
    runs = last_runs(session)
    who = queries.people(session, [r.started_by for r in runs.values()])
    return [{"job": name, "label": job.label, "every_hours": int(job.every.total_seconds() // 3600),
             "last_run": run_view(runs[name], who) if name in runs else None,
             "next_due": (runs[name].started_at + job.every) if name in runs else None} for name, job in JOBS.items()]
