"""Adding a finding from an outside system to a case, and reading what was imported (docs/case-management/09, 13).

How a finding enters a case (docs/case-management/03 §5, "Add to case"):
1. The source system is identified by its key (sources.authenticate), the person by their own login. The finding is
   added for that person, with exactly their rights (engine rights: someone who may add files to the case).
2. The source's policy is checked (sources.check_policy), then the finding itself (contract.py, indicators.py).
3. It becomes a file of type `import` in the case's "imports" folder, with its own entry in the case's history
   (`import_added`). So it is searched and reported like everything else in the case.
4. Its provenance is kept permanently (integration_imports): source, record ID, source hash, payload reference,
   legal authority, when it happened, which key sent it, and for whom. The identifiers it names are
   indexed (integration_indicators), so the same phone number or IP address is found in other cases.
5. The caller writes the audit event, in the same transaction.

A finding is never edited. If its source changes the record later (a different source hash), sending it again adds
a new version of the same file; earlier versions stay. Sending the same record twice is refused. A finding that was
withdrawn and is sent again becomes a new file; the withdrawn one stays. Only references, hashes and derived results are
stored: raw data (log files, CDR or IPDR dumps) stays in its source system.
"""

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select, tuple_
from sqlalchemy.orm import Session

from app.casemgmt import engine, hashing, history, queries
from app.casemgmt.access import hidden_file_ids, require, rights, supervises
from app.casemgmt.enums import ArtifactType, FileStatus, HistoryKind, MemberRole
from app.casemgmt.errors import Conflict, Invalid, NotVisible
from app.casemgmt.integrations import contract, indicators
from app.casemgmt.integrations.sources import check_policy, source_ref
from app.casemgmt.links import _openable
from app.casemgmt.models import (
    Artifact,
    ArtifactVersion,
    CaseEntry,
    CaseFamily,
    CaseLink,
    CaseMember,
    IntegrationImport,
    IntegrationIndicator,
    IntegrationSource,
)
from app.casemgmt.notifications import notify
from app.db.models import User

FOLDER = "imports"


@dataclass
class Finding:
    """One finding as an outside system sends it (the integration contract)."""

    item_type: str
    source_record_id: str
    source_hash: str
    summary: str
    title: str | None = None
    payload_ref: str | None = None
    authority_ref: str | None = None
    observed_at: dt.datetime | None = None
    observed_until: dt.datetime | None = None
    identifiers: list[dict] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    message: str | None = None


@dataclass
class Imported:
    entry: CaseEntry
    artifact: Artifact
    version: ArtifactVersion
    record: IntegrationImport
    updated: bool  # a new version of a record imported before (its source changed it)


def _details(details: Any) -> dict:
    if not isinstance(details, dict):
        raise Invalid("details must be a JSON object")
    if len(hashing.canonical_json(details)) > contract.MAX_DETAILS_BYTES:
        raise Invalid(f"details: at most {contract.MAX_DETAILS_BYTES:,} bytes. Raw data stays in the source system: "
                      "send a reference to it (payload_ref) and the derived result")
    return details


def _leads(session: Session, family: CaseFamily) -> list[uuid.UUID]:
    return list(session.scalars(select(CaseMember.user_id).where(
        CaseMember.case_family_id == family.id, CaseMember.role == MemberRole.LEAD.value, CaseMember.revoked_at.is_(None))))


def add_to_case(session: Session, actor: User, family: CaseFamily, source: IntegrationSource, finding: Finding, *,
                key_prefix: str | None) -> Imported:
    """Add one finding to a case the person may add to. Everything is checked before anything is written."""
    family = engine._lock_family(session, family.id)
    found = rights(session, actor, family)
    require(found.add_files, "You can read this case but not add to it", found)
    kind = contract.item_type(finding.item_type)
    authority = contract.text(finding.authority_ref, "authority_ref", 300)
    check_policy(source, family, kind.value, authority)
    record = contract.record_id(finding.source_record_id)
    digest = contract.source_hash(finding.source_hash)
    summary = contract.text(finding.summary, "summary (what was found, in a few sentences)", contract.MAX_SUMMARY, minimum=10)
    title = contract.text(finding.title, "title", 300) or f"{contract.label(kind)}: {record}"[:300]
    payload_ref = contract.text(finding.payload_ref, "payload_ref", 500)
    message = contract.text(finding.message, "message", 2000)
    observed_at, observed_tz, observed_until = contract.period(kind, finding.observed_at, finding.observed_until)
    identifiers = indicators.parse_all(finding.identifiers or [])
    if kind.value == "indicator" and not identifiers:
        raise Invalid("An indicator needs at least one identifier (ip, domain, url, email, phone, imei, imsi, account, file_hash)")
    details = _details(finding.details or {})

    content = {
        "item_type": kind.value, "summary": summary, "source_record_id": record, "source_hash": digest,
        "source": {"code": source.code, "name": source.name, "kind": source.kind, "fictional": source.fictional},
        "payload_ref": payload_ref, "authority_ref": authority,
        "observed_at": finding.observed_at.isoformat() if finding.observed_at else None,
        "observed_until": finding.observed_until.isoformat() if finding.observed_until else None,
        "identifiers": identifiers, "details": details, "contract_version": contract.CONTRACT_VERSION,
    }
    before = session.scalar(select(IntegrationImport).where(
        IntegrationImport.case_family_id == family.id, IntegrationImport.source_id == source.id,
        IntegrationImport.source_record_id == record).order_by(IntegrationImport.imported_at.desc(), IntegrationImport.id).limit(1))
    artifact = session.get(Artifact, before.artifact_id) if before is not None else None
    folder = engine.ensure_folder(session, family, actor, FOLDER, system=True)
    if artifact is None or artifact.status != FileStatus.ACTIVE.value:
        # a record not in the case yet, or one that was withdrawn: a file of its own
        artifact, version = engine._new_version(session, family=family, folder=folder, artifact=None, artifact_type=ArtifactType.IMPORT,
                                                title=title, content=content, author=actor)
        updated = False
    else:
        if before.source_hash == digest:
            raise Conflict(f"{artifact.display_id} already holds this record, exactly as received: nothing changed",
                           existing={"artifact_id": str(artifact.id), "display_id": artifact.display_id})
        current = engine.latest_version(session, artifact)
        note = f"Updated in {source.name}: the record's hash changed from {before.source_hash} to {digest}"
        artifact, version = engine._new_version(session, family=family, folder=None, artifact=artifact, artifact_type=ArtifactType.IMPORT,
                                                title=artifact.title, content=content, author=actor, change_note=note,
                                                derived_from=[str(current.id)])
        updated = True

    text = message or f"{contract.label(kind)} {record} from {source.name}" + (" (updated at the source)" if updated else "")
    entry = history.append(session, family, actor, HistoryKind.IMPORT_ADDED, f"{artifact.display_id} {text}"[:500], subject_type="artifact",
                           subject_id=artifact.id,
                           details={"display_id": artifact.display_id, "source": source.code, "item_type": kind.value, "record": record,
                                    "source_hash": digest, "updated": updated, "content_sha256": version.content_sha256})
    row = IntegrationImport(organization_id=family.organization_id, source_id=source.id, case_family_id=family.id, artifact_id=artifact.id,
                            artifact_version_id=version.id, item_type=kind.value, source_record_id=record, source_hash=digest,
                            payload_ref=payload_ref, authority_ref=authority, observed_at=observed_at, observed_tz=observed_tz,
                            observed_until=observed_until, key_prefix=key_prefix, imported_by=actor.id)
    session.add(row)
    session.flush()
    session.add_all(IntegrationIndicator(import_id=row.id, organization_id=family.organization_id, case_family_id=family.id,
                                         indicator_type=i["type"], value=i["value"]) for i in identifiers)
    session.flush()
    notify(session, _leads(session, family), "import.added", family=family, actor=actor,
           artifact={"id": artifact.id, "display_id": artifact.display_id}, item_type=contract.label(kind), source=source.name)
    return Imported(entry, artifact, version, row, updated)


# ---------------------------------------------------------------- reading


def _describe(artifact: Artifact, version: ArtifactVersion, row: IntegrationImport | None, versions: int, sources: dict, who: dict) -> dict:
    content = version.content or {}
    source = sources.get(row.source_id) if row else None
    return {
        "artifact_id": artifact.id, "display_id": artifact.display_id, "status": artifact.status,
        "withdrawn_reason": artifact.withdrawn_reason, "title": artifact.title, "version_number": version.version_number, "versions": versions,
        "item_type": content.get("item_type"), "item_type_label": contract.label(str(content.get("item_type"))),
        "summary": content.get("summary"),
        "source": source_ref(source) if source else {**(content.get("source") or {}), "id": None, "kind_label": None, "status": None},
        "source_record_id": content.get("source_record_id"), "source_hash": content.get("source_hash"),
        "payload_ref": content.get("payload_ref"), "authority_ref": content.get("authority_ref"),
        "observed_at": content.get("observed_at"), "observed_until": content.get("observed_until"),
        "identifiers": [{"type": i["type"], "label": indicators.label(i["type"]), "value": i["value"]} for i in content.get("identifiers", [])],
        "imported_by": who.get(row.imported_by) if row else who.get(version.author_id),
        "imported_at": row.imported_at if row else version.created_at,
        "received_with": row.key_prefix if row else None,
        "content_sha256": version.content_sha256, "fictional": bool((content.get("source") or {}).get("fictional")),
    }


def _visible_imports(session: Session, viewer: User, family: CaseFamily) -> list[Artifact]:
    hidden = hidden_file_ids(session, viewer, family)
    return [a for a in session.scalars(select(Artifact).where(Artifact.case_family_id == family.id,
                                                              Artifact.artifact_type == ArtifactType.IMPORT.value)
                                       .order_by(Artifact.created_at, Artifact.display_id)) if a.id not in hidden]


def _load(session: Session, artifacts: list[Artifact]) -> tuple[dict, dict, dict, dict, dict]:
    """(latest version, the import row of that version, version counts, sources, people) for these artifacts."""
    ids = [a.id for a in artifacts]
    latest: dict = {}
    counts: dict = {}
    for version in session.scalars(select(ArtifactVersion).where(ArtifactVersion.artifact_id.in_(ids)).order_by(ArtifactVersion.version_number)) if ids else []:
        latest[version.artifact_id] = version
        counts[version.artifact_id] = counts.get(version.artifact_id, 0) + 1
    rows = {r.artifact_version_id: r for r in session.scalars(select(IntegrationImport).where(
        IntegrationImport.artifact_version_id.in_([v.id for v in latest.values()])))} if latest else {}
    sources = {s.id: s for s in session.scalars(select(IntegrationSource).where(
        IntegrationSource.id.in_({r.source_id for r in rows.values()})))} if rows else {}
    who = queries.people(session, [r.imported_by for r in rows.values()] + [v.author_id for v in latest.values()])
    return latest, rows, counts, sources, who


def described(session: Session, imported: Imported) -> dict:
    """A finding just added, as the list of imports shows it."""
    latest, rows, counts, sources, who = _load(session, [imported.artifact])
    return _describe(imported.artifact, imported.version, rows.get(imported.version.id), counts.get(imported.artifact.id, 1), sources, who)


def imports_of(session: Session, viewer: User, family: CaseFamily) -> dict:
    """The findings imported into the case (withdrawn ones too, marked so)."""
    artifacts = _visible_imports(session, viewer, family)
    latest, rows, counts, sources, who = _load(session, artifacts)
    keyed = []
    for artifact in artifacts:
        version = latest[artifact.id]
        row = rows.get(version.id)
        when = (row.observed_at or row.imported_at) if row else version.created_at
        keyed.append((when, _describe(artifact, version, row, counts.get(artifact.id, 1), sources, who)))
    keyed.sort(key=lambda pair: (pair[0], pair[1]["display_id"]), reverse=True)  # what happened most recently first
    items = [item for _, item in keyed]
    by_type: dict[str, int] = {}
    for item in items:
        if item["status"] == FileStatus.ACTIVE.value:
            by_type[item["item_type"]] = by_type.get(item["item_type"], 0) + 1
    return {"case": queries.case_ref(family), "imports": items, "by_type": by_type, "item_types": contract.describe()["item_types"]}


def _linked_families(session: Session, family: CaseFamily) -> set[str]:
    """Cases this case links to (active links), by case ID."""
    return {str(i) for i in session.scalars(
        select(CaseLink.target_family_id).join(Artifact, Artifact.id == CaseLink.artifact_id)
        .where(CaseLink.case_family_id == family.id, CaseLink.target_family_id.is_not(None), Artifact.status == FileStatus.ACTIVE.value))}


def other_cases(session: Session, viewer: User, family: CaseFamily, pairs: set[tuple[str, str]]) -> dict[tuple[str, str], list[dict]]:
    """Where else these identifiers were imported: only in cases the viewer can open, and only findings they may see there
    (active, and not sealed unless they supervise that case)."""
    if not pairs:
        return {}
    rows = session.execute(
        select(IntegrationIndicator.indicator_type, IntegrationIndicator.value, IntegrationImport)
        .join(IntegrationImport, IntegrationImport.id == IntegrationIndicator.import_id)
        .where(IntegrationIndicator.organization_id == family.organization_id, IntegrationIndicator.case_family_id != family.id,
               tuple_(IntegrationIndicator.indicator_type, IntegrationIndicator.value).in_(sorted(pairs)))
        .order_by(IntegrationImport.imported_at)).all()
    if not rows:
        return {}
    openable = _openable(session, viewer, {r[2].case_family_id for r in rows})
    artifact_ids = {r[2].artifact_id for r in rows if r[2].case_family_id in openable}
    artifacts = {a.id: a for a in session.scalars(select(Artifact).where(Artifact.id.in_(artifact_ids)))} if artifact_ids else {}
    named = select(IntegrationSource.id, IntegrationSource.name).where(IntegrationSource.id.in_({r[2].source_id for r in rows}))
    names = {i: n for i, n in session.execute(named)}
    found: dict[tuple[str, str], dict[uuid.UUID, dict]] = {}
    for kind, value, row in rows:
        other = openable.get(row.case_family_id)
        if other is None:
            continue
        artifact = artifacts[row.artifact_id]
        if artifact.status != FileStatus.ACTIVE.value or (artifact.sealed and not supervises(viewer, other)):
            continue
        case = found.setdefault((kind, value), {}).setdefault(other.id, {"case": queries.case_ref(other), "imports": []})
        if all(i["display_id"] != artifact.display_id for i in case["imports"]):
            case["imports"].append({"display_id": artifact.display_id, "title": artifact.title, "item_type": row.item_type,
                                    "item_type_label": contract.label(row.item_type), "source": names.get(row.source_id),
                                    "imported_at": row.imported_at})
    return {pair: list(cases.values()) for pair, cases in found.items()}


def import_detail(session: Session, viewer: User, family: CaseFamily, artifact_id: uuid.UUID) -> dict:
    """One imported finding: its provenance, every version, what uses it, and where else its identifiers appear."""
    artifacts = _visible_imports(session, viewer, family)
    artifact = next((a for a in artifacts if a.id == artifact_id), None)
    if artifact is None:
        raise NotVisible()
    latest, rows, counts, sources, who = _load(session, [artifact])
    version = latest[artifact.id]
    item = _describe(artifact, version, rows.get(version.id), counts.get(artifact.id, 1), sources, who)

    every = list(session.scalars(select(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact.id).order_by(ArtifactVersion.version_number)))
    history_rows = {r.artifact_version_id: r for r in session.scalars(select(IntegrationImport).where(
        IntegrationImport.artifact_version_id.in_([v.id for v in every])))}
    people = queries.people(session, [r.imported_by for r in history_rows.values()])
    versions = [{"version_number": v.version_number, "source_hash": (v.content or {}).get("source_hash"), "change_note": v.change_note,
                 "imported_by": people.get(history_rows[v.id].imported_by) if v.id in history_rows else None,
                 "imported_at": history_rows[v.id].imported_at if v.id in history_rows else v.created_at,
                 "received_with": history_rows[v.id].key_prefix if v.id in history_rows else None,
                 "content_sha256": v.content_sha256, "current": v.id == version.id} for v in every]

    mine = [str(v.id) for v in every]
    hidden = hidden_file_ids(session, viewer, family)
    derived = session.execute(select(ArtifactVersion, Artifact).join(Artifact, ArtifactVersion.artifact_id == Artifact.id).where(
        Artifact.case_family_id == family.id, Artifact.id != artifact.id, Artifact.status == FileStatus.ACTIVE.value,
        or_(*[ArtifactVersion.derived_from.contains([v]) for v in mine]))).all() if mine else []
    used_by = [{"artifact_id": a.id, "display_id": a.display_id, "title": a.title, "artifact_type": a.artifact_type,
                "version_number": v.version_number} for v, a in derived if a.id not in hidden]

    content = version.content or {}
    pairs = {(i["type"], i["value"]) for i in content.get("identifiers", [])}
    elsewhere = other_cases(session, viewer, family, pairs)
    linked = _linked_families(session, family)
    here = _in_this_case(session, [a for a in artifacts if a.id != artifact.id], pairs)
    item["identifiers"] = [{"type": i["type"], "label": indicators.label(i["type"]), "value": i["value"], "as_received": i.get("as_received"),
                            "in_this_case": here.get((i["type"], i["value"]), []),
                            "other_cases": [{**c, "linked": str(c["case"]["id"]) in linked} for c in elsewhere.get((i["type"], i["value"]), [])]}
                           for i in content.get("identifiers", [])]
    return {**item, "case": queries.case_ref(family), "details": content.get("details") or {},
            "history": versions, "used_by": used_by,
            "policy_note": "Raw data stays in the source system: this case keeps the reference, the hash and the derived result."}


def _in_this_case(session: Session, artifacts: list[Artifact], pairs: set[tuple[str, str]]) -> dict[tuple[str, str], list[str]]:
    """Other imported findings of the case naming the same identifiers (display IDs)."""
    if not pairs or not artifacts:
        return {}
    names = {a.id: a.display_id for a in artifacts}
    found: dict[tuple[str, str], list[str]] = {}
    latest: dict = {}
    for version in session.scalars(select(ArtifactVersion).where(ArtifactVersion.artifact_id.in_(list(names))).order_by(ArtifactVersion.version_number)):
        latest[version.artifact_id] = version
    for version in latest.values():
        for i in (version.content or {}).get("identifiers", []):
            pair = (i["type"], i["value"])
            if pair in pairs and names[version.artifact_id] not in found.get(pair, []):
                found.setdefault(pair, []).append(names[version.artifact_id])
    return found


def indicators_of(session: Session, viewer: User, family: CaseFamily) -> dict:
    """Every identifier the case's imported findings name, and the other cases where it appears."""
    artifacts = _visible_imports(session, viewer, family)
    latest, *_ = _load(session, artifacts)
    grouped: dict[tuple[str, str], dict] = {}
    for artifact in artifacts:
        version = latest[artifact.id]
        for i in (version.content or {}).get("identifiers", []):
            pair = (i["type"], i["value"])
            group = grouped.setdefault(pair, {"type": i["type"], "label": indicators.label(i["type"]), "value": i["value"], "imports": []})
            group["imports"].append({"artifact_id": artifact.id, "display_id": artifact.display_id, "status": artifact.status,
                                     "item_type_label": contract.label(str((version.content or {}).get("item_type")))})
    elsewhere = other_cases(session, viewer, family, set(grouped))
    linked = _linked_families(session, family)
    result = []
    for pair, group in grouped.items():
        group["imports"].sort(key=lambda i: i["display_id"])
        group["other_cases"] = [{**c, "linked": str(c["case"]["id"]) in linked} for c in elsewhere.get(pair, [])]
        result.append(group)
    result.sort(key=lambda g: (-len(g["other_cases"]), -len(g["imports"]), g["type"], g["value"]))
    cases = {c["case"]["id"] for g in result for c in g["other_cases"]}
    return {"case": queries.case_ref(family), "indicators": result,
            "totals": {"identifiers": len(result), "with_matches": sum(1 for g in result if g["other_cases"]), "cases": len(cases)},
            "note": "Matches are shown only in cases you can open, and only findings you may see there."}
