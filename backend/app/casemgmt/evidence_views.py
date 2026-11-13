"""Read-only views of evidence for the API: summaries, details, custody and the integrity report.

Visibility is decided before these run (evidence.get_evidence, access.hidden_file_ids); sealed or too highly
classified exhibits never reach them for people who may not see them.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.casemgmt import custody, queries
from app.casemgmt.access import family_condition, rights, supervises
from app.casemgmt.custody import CustodyState
from app.casemgmt.enums import FileStatus, IntegrityResult
from app.casemgmt.evidence import Seen
from app.casemgmt.models import (
    CaseFamily,
    CaseFolder,
    CustodyEvent,
    EvidenceItem,
    EvidenceSourceReference,
    EvidenceVersion,
    IntegrityCheck,
)
from app.db.models import User


def evidence_ref(item: EvidenceItem) -> dict:
    return {"id": item.id, "display_id": item.display_id, "title": item.title}


def last_checks(session: Session, shas) -> dict[str, IntegrityCheck]:
    """The latest integrity check of each object."""
    shas = list(set(shas))
    if not shas:
        return {}
    rows = session.scalars(select(IntegrityCheck).where(IntegrityCheck.object_sha256.in_(shas))
                           .order_by(IntegrityCheck.object_sha256, IntegrityCheck.checked_at.desc(), IntegrityCheck.id.desc())
                           .ext(distinct_on(IntegrityCheck.object_sha256)))
    return {check.object_sha256: check for check in rows}


def check_view(check: IntegrityCheck | None, who: dict) -> dict | None:
    if check is None:
        return None
    return {"result": check.result, "trigger": check.trigger, "checked_at": check.checked_at, "checked_by": who.get(check.checked_by),
            "recorded_sha256": check.object_sha256, "computed_sha256": check.computed_sha256}


def custodian(user_id, name, who: dict) -> dict | None:
    if user_id is None and name is None:
        return None
    return {"user": who.get(user_id), "name": name}


def event_view(event: CustodyEvent, who: dict) -> dict:
    return {"id": event.id, "event_type": event.event_type, "actor": who.get(event.actor_id),
            "from_custodian": custodian(event.from_custodian_id, event.from_custodian_name, who),
            "to_custodian": custodian(event.to_custodian_id, event.to_custodian_name, who),
            "occurred_at": event.occurred_at, "occurred_tz": event.occurred_tz, "recorded_at": event.recorded_at,
            "reason": event.reason, "method": event.method, "verification_sha256": event.verification_sha256,
            "related_event_id": event.related_event_id, "authorization_ref": event.authorization_ref, "details": event.details}


def summaries(session: Session, pairs: list[tuple[EvidenceItem, EvidenceVersion]]) -> dict[uuid.UUID, dict]:
    """EvidenceSummary for each (item, version), with custodian and latest integrity check."""
    states = custody.states(session, [item.id for item, _ in pairs])
    folders = {f.id: f.name for f in session.scalars(select(CaseFolder).where(CaseFolder.id.in_({i.folder_id for i, _ in pairs})))}
    checks = last_checks(session, [v.object_sha256 for _, v in pairs])
    who = queries.people(session, [v.uploaded_by for _, v in pairs]
                         + [s.custodian_id for s in states.values()] + [c.checked_by for c in checks.values()])
    found = {}
    for item, version in pairs:
        state = states[item.id]
        found[item.id] = {
            **evidence_ref(item), "folder": folders.get(item.folder_id, ""), "status": item.status,
            "evidence_type": item.evidence_type, "category": item.category,
            "classification": item.classification, "sealed": item.sealed, "sha256": version.object_sha256,
            "size_bytes": version.size_bytes, "mime_type": version.mime_type, "original_filename": version.original_filename,
            "active_content": version.active_content, "collected_at": item.collected_at,
            "uploaded_by": who.get(version.uploaded_by), "uploaded_at": version.uploaded_at,
            "custodian": custodian(state.custodian_id, state.custodian_name, who),
            "last_check": check_view(checks.get(version.object_sha256), who),
        }
    return found


def version_view(session: Session, version: EvidenceVersion, who: dict) -> dict:
    return {"id": version.id, "version_number": version.version_number, "original_filename": version.original_filename,
            "display_filename": version.display_filename, "mime_type": version.mime_type,
            "declared_mime_type": version.declared_mime_type, "size_bytes": version.size_bytes, "sha256": version.object_sha256,
            "uploaded_by": who.get(version.uploaded_by), "uploaded_at": version.uploaded_at}


def detail(session: Session, user: User, seen: Seen) -> dict:
    item, version, family = seen.item, seen.version, seen.family
    summary = summaries(session, [(item, version)])[item.id]
    state: CustodyState = custody.state(session, seen)
    sources = list(session.scalars(select(EvidenceSourceReference).where(EvidenceSourceReference.evidence_version_id == version.id)))
    who = queries.people(session, [item.created_by, item.sealed_by, version.uploaded_by, *(s.imported_by for s in sources),
                                   *(e.actor_id for e in state.events), *(e.to_custodian_id for e in state.events),
                                   *(e.from_custodian_id for e in state.events)])
    is_supervisor = supervises(user, family)
    found = rights(session, user, family)
    pending = state.pending
    return {
        **summary, "case": queries.case_ref(family), "description": item.description, "source": item.source,
        "collected_tz": item.collected_tz, "collected_by": item.collected_by, "collection_authority": item.collection_authority,
        "created_by": who.get(item.created_by), "version": version_view(session, version, who),
        "sources": [{"source_system": s.source_system, "source_record_id": s.source_record_id, "source_hash": s.source_hash,
                     "original_reference": s.original_reference, "imported_by": who.get(s.imported_by),
                     "imported_at": s.imported_at} for s in sources],
        "sealed_reason": item.sealed_reason, "sealed_by": who.get(item.sealed_by), "sealed_at": item.sealed_at,
        "withdrawn_reason": item.withdrawn_reason, "withdrawn_at": item.withdrawn_at,
        "pending_transfer": event_view(pending, who) if pending else None,
        "can": {"verify": True, "download": True, "preview": not version.active_content,
                "transfer": pending is None and (state.custodian_id == user.id or is_supervisor),
                "acknowledge": pending is not None and pending.to_custodian_id == user.id,
                "seal": is_supervisor and not item.sealed, "unseal": is_supervisor and item.sealed,
                "withdraw": found.withdraw and item.status == FileStatus.ACTIVE.value, "add_derived": found.add_files},
    }


def custody_view(session: Session, seen: Seen) -> dict:
    state = custody.state(session, seen)
    who = queries.people(session, [e.actor_id for e in state.events] + [e.to_custodian_id for e in state.events]
                         + [e.from_custodian_id for e in state.events])
    return {"evidence": evidence_ref(seen.item), "current_custodian": custodian(state.custodian_id, state.custodian_name, who),
            "pending_transfer": event_view(state.pending, who) if state.pending else None,
            "events": [event_view(e, who) for e in state.events]}


def integrity_report(session: Session, admin: User, *, limit: int, offset: int) -> tuple[dict, list[dict], int]:
    """Every exhibit of the admin's organisation (within their clearance) with its latest check; failures first."""
    pairs = session.execute(
        select(EvidenceItem, EvidenceVersion, CaseFamily)
        .join(EvidenceVersion, EvidenceVersion.evidence_item_id == EvidenceItem.id)
        .join(CaseFamily, CaseFamily.id == EvidenceItem.case_family_id)
        .where(family_condition(admin))
    ).all()
    checks = last_checks(session, [v.object_sha256 for _, v, _ in pairs])
    who = queries.people(session, [c.checked_by for c in checks.values()])
    order = {IntegrityResult.MISMATCH: 0, IntegrityResult.MISSING: 0, None: 1, IntegrityResult.MATCH: 2}
    counts = {"match": 0, "mismatch": 0, "missing": 0, "never_checked": 0}
    rows = []
    for item, version, family in pairs:
        check = checks.get(version.object_sha256)
        counts[check.result if check else "never_checked"] += 1
        rows.append(((order[check.result if check else None], check.checked_at.timestamp() if check else 0, item.display_id),
                     {"evidence": evidence_ref(item), "case": queries.case_ref(family), "sha256": version.object_sha256,
                      "size_bytes": version.size_bytes, "sealed": item.sealed, "last_check": check_view(check, who)}))
    rows.sort(key=lambda row: row[0])
    return counts, [row for _, row in rows[offset:offset + limit]], len(rows)
