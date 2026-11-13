"""A case report preview (spec §21 screen 19 and §22): what a report about the case, as it stands now, contains.

It describes the case as of one history entry (the latest when it is made), so it states exactly that state:
- the case, its folders and its team;
- the evidence, with hashes, the current custodian and the latest integrity check;
- the notes and analyses;
- the findings imported from outside systems, with their provenance;
- whether the case's history is intact.

Only what the viewer may see is included. Sealed exhibits are left out for those who may not see them, and
the report says how many files were left out.

The preview is for reading and printing. Signed, versioned PDF reports that can be verified later are built from it
(governance/reports.py), with only what every member of the case may see (shared=True). No report is represented as automatically
admissible in court.
"""

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casemgmt import custody, evidence_views, history, queries
from app.casemgmt.access import hidden_file_ids
from app.casemgmt.enums import ArtifactType, FileStatus
from app.casemgmt.intelligence.scope import shared_hidden_ids
from app.casemgmt.models import (
    Artifact,
    ArtifactVersion,
    CaseFamily,
    CaseFolder,
    EvidenceItem,
    EvidenceVersion,
    IntegrationImport,
    IntegrationSource,
)
from app.db.models import User

DISCLAIMER = ("Generated from the case's permanent history for review. It is not automatically admissible in court: admissibility "
              "is for the competent court to decide under the applicable rules of evidence and procedure.")
PREVIEW_NOTE = ("Preview of what you may see. A signed PDF report (Generate a signed PDF) contains what every member of the case may "
                "see, is kept unchanged and can be checked later. Printing this page does not create a report version.")
# What the report lists as notes and analyses: not the generated or received kinds, which have their own place.
NOTE_TYPES = {ArtifactType.CASE_SUMMARY.value, ArtifactType.OFFICIAL_REFERENCES.value, ArtifactType.NOTE.value,
              ArtifactType.ANALYSIS.value, ArtifactType.TRANSCRIPTION.value, ArtifactType.TIMELINE.value}


def report_preview(session: Session, viewer: User, family: CaseFamily, *, shared: bool = False) -> dict:
    """What a report on the case as it is now contains: for the viewer, or (shared=True, the signed PDF reports) only what
    everyone on the case may see, since every member can open the report."""
    hidden = shared_hidden_ids(session, family) if shared else hidden_file_ids(session, viewer, family)
    folders = {f.id: f.name for f in session.scalars(select(CaseFolder).where(CaseFolder.case_family_id == family.id))}

    pairs = [(i, v) for i, v in session.execute(
        select(EvidenceItem, EvidenceVersion).join(EvidenceVersion, EvidenceVersion.evidence_item_id == EvidenceItem.id)
        .where(EvidenceItem.case_family_id == family.id).order_by(EvidenceItem.created_at, EvidenceItem.display_id)).all()]
    shown = [(i, v) for i, v in pairs if i.id not in hidden]
    described = evidence_views.summaries(session, shown) if shown else {}
    holders = custody.states(session, [i.id for i, _ in shown]) if shown else {}
    who = queries.people(session, [v.uploaded_by for _, v in shown])
    evidence = []
    for item, version in shown:
        holder = holders.get(item.id)
        evidence.append({
            **described[item.id], "item_id": item.id, "folder": folders.get(item.folder_id, ""), "original_filename": version.original_filename,
            "collected_at": item.collected_at, "collected_by": item.collected_by, "collection_authority": item.collection_authority,
            "source": item.source, "uploaded_by": who.get(version.uploaded_by), "uploaded_at": version.uploaded_at,
            "withdrawn_reason": item.withdrawn_reason,
            "transfer_pending": bool(holder and holder.pending),
        })

    all_artifacts = list(session.scalars(select(Artifact).where(Artifact.case_family_id == family.id)
                                         .order_by(Artifact.created_at, Artifact.display_id)))
    artifacts_shown = [a for a in all_artifacts if a.id not in hidden]
    latest: dict[uuid.UUID, ArtifactVersion] = {}
    for version in session.scalars(select(ArtifactVersion).where(ArtifactVersion.artifact_id.in_([a.id for a in artifacts_shown]))
                                   .order_by(ArtifactVersion.version_number)) if artifacts_shown else []:
        latest[version.artifact_id] = version
    authors = queries.people(session, [v.author_id for v in latest.values()])
    notes = [{"display_id": a.display_id, "title": a.title, "artifact_type": a.artifact_type, "folder": folders.get(a.folder_id, ""),
              "status": a.status, "withdrawn_reason": a.withdrawn_reason, "version_number": latest[a.id].version_number,
              "version_created_at": latest[a.id].created_at, "author": authors.get(latest[a.id].author_id),
              "change_note": latest[a.id].change_note}
             for a in artifacts_shown if a.artifact_type in NOTE_TYPES]
    imports = _imports(session, [a for a in artifacts_shown if a.artifact_type == ArtifactType.IMPORT.value], latest, authors)

    integrity = {"match": 0, "mismatch": 0, "missing": 0, "never_checked": 0}
    for item in evidence:
        if item["status"] == FileStatus.ACTIVE.value:
            integrity[item["last_check"]["result"] if item["last_check"] else "never_checked"] += 1
    references = queries._references(session, [family.id]).get(family.id, [])
    checked = history.verify_chain(session, family.id)
    team = queries.team_rows(session, family)
    withheld = len(pairs) - len(shown) + len(all_artifacts) - len(artifacts_shown)
    return {
        "case": {**queries.case_ref(family), "description": family.description, "jurisdiction": family.jurisdiction,
                 "official_status": family.official_status, "references": [queries.reference_label(r) for r in references]},
        "folders": [f["name"] for f in queries.folders_of(session, viewer, family, hidden)],
        "history": {"entries": checked["entries"], "intact": checked["intact"]},
        "evidence": evidence,
        "artifacts": notes,
        "imports": imports,
        "integrity": integrity,
        "team": team,
        "withheld_entries": withheld,
        "generated_at": dt.datetime.now(dt.UTC),
        "generated_by": queries.people(session, [viewer.id]).get(viewer.id),
        "disclaimer": DISCLAIMER,
        "preview_note": PREVIEW_NOTE,
    }


def _imports(session: Session, artifacts: list[Artifact], latest: dict, who: dict) -> list[dict]:
    """Findings imported from outside systems in the case, with where each came from."""
    ids = [latest[a.id].id for a in artifacts]
    rows = {r.artifact_version_id: r for r in session.scalars(select(IntegrationImport).where(IntegrationImport.artifact_version_id.in_(ids)))} \
        if ids else {}
    named = select(IntegrationSource.id, IntegrationSource.name).where(IntegrationSource.id.in_({r.source_id for r in rows.values()}))
    names = {i: n for i, n in session.execute(named)} if rows else {}
    people = queries.people(session, [r.imported_by for r in rows.values()])
    found = []
    for artifact in artifacts:
        version = latest[artifact.id]
        row = rows.get(version.id)
        content = version.content or {}
        found.append({"status": artifact.status, "display_id": artifact.display_id, "title": artifact.title,
                      "item_type": content.get("item_type"),
                      "source": names.get(row.source_id) if row else (content.get("source") or {}).get("name"),
                      "source_record_id": content.get("source_record_id"), "source_hash": content.get("source_hash"),
                      "authority_ref": content.get("authority_ref"), "observed_at": content.get("observed_at"),
                      "imported_by": people.get(row.imported_by) if row else who.get(version.author_id),
                      "imported_at": row.imported_at if row else None, "version_number": version.version_number,
                      "fictional": bool((content.get("source") or {}).get("fictional"))})
    return found

