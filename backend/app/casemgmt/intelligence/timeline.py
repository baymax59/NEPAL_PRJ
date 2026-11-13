"""The reconstructed timeline (docs/case-management/02 Part C.4; 04 §10).

Dates found in the text of the case's documents and notes (the existing rule-based date extraction,
app/extraction/timeline.py), each with the sentence around it, its exhibit or note, version and page; plus the
dates the records hold (when each exhibit was collected, official references). It is stored as a note of
type `timeline` in the case's "timeline" folder, with a history entry of its own (`timeline_generated`). Rebuilding it creates a new
version; earlier versions stay in the history, nothing is overwritten.

It becomes part of the case record, which everyone on the case reads. So it is built from the *shared* view
(scope.py): sealed exhibits and notes, and exhibits classified above the case, are never used, whoever rebuilds it.
"""

import datetime as dt
import uuid

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.casemgmt import engine, history, queries
from app.casemgmt.access import hidden_file_ids, require, rights
from app.casemgmt.enums import ArtifactType, FileStatus, HistoryKind, TextSourceKind, TextStatus
from app.casemgmt.errors import Invalid
from app.casemgmt.integrations import contract
from app.casemgmt.intelligence import index
from app.casemgmt.intelligence.scope import GENERATED_TYPES, Source, sources
from app.casemgmt.models import (
    Artifact,
    ArtifactVersion,
    CaseFamily,
    CaseFolder,
    CaseOfficialReference,
    EvidenceItem,
    IntegrationImport,
    ObjectPage,
)
from app.casemgmt.storage import EvidenceStore
from app.db.models import User
from app.embeddings.model import Embedder
from app.extraction.timeline import events_from_pages

FOLDER = "timeline"
TIMELINE_TITLE = "Reconstructed timeline"
MAX_EVENTS = 400
EVIDENCE_SECONDS = 60  # time to read documents not read yet, before building
NOT_USED_TYPES = {ArtifactType.LINK.value, *GENERATED_TYPES}
METHOD = (
    "Built automatically: dates written in the case's documents and notes, each with the sentence around it "
    "(rule-based date recognition, the same as for past cases), plus dates from the records (when exhibits were "
    "collected, official references). Dates are kept between 1900 and today. A sentence that only cites another "
    "judgment is skipped. Check each entry against its source before relying on it."
)
SHARED_NOTE = ("Sealed exhibits and notes, and exhibits classified above the case, are never used, so everyone on the "
               "case may read this timeline.")


def _source_ref(source: Source) -> dict:
    return {"kind": source.kind.value, "display_id": source.display_id, "title": source.title, "path": source.path,
            "version_number": source.version_number, "version_id": str(source.version_id), "item_id": str(source.item_id)}


def _local_date(moment: dt.datetime, tz: str | None) -> dt.date:
    """The date where it happened: the time is stored in UTC with the timezone it was given in ("+05:30")."""
    if tz:
        sign = -1 if tz.startswith("-") else 1
        hours, minutes = tz.lstrip("+-").split(":")
        return (moment + sign * dt.timedelta(hours=int(hours), minutes=int(minutes))).date()
    return moment.date()


def build_events(session: Session, family: CaseFamily, sources: list[Source]) -> tuple[list[dict], list[dict], list[dict]]:
    """(events in date order, sources used with their event counts, sources not used and why)."""
    events: list[dict] = []
    used: dict[str, dict] = {}
    not_used: list[dict] = []
    texts = index.texts_for(session, (s.key for s in sources))
    readable = []
    for source in sources:
        text = texts.get(source.key)
        if source.artifact_type in NOT_USED_TYPES:
            continue
        if (reason := index.unreadable_reason(source)) is not None:
            if source.kind == TextSourceKind.EVIDENCE:
                not_used.append({"display_id": source.display_id, "reason": reason})
        elif text is None:
            not_used.append({"display_id": source.display_id, "reason": "not read yet (try again in a minute)"})
        elif text.status != TextStatus.INDEXED:
            not_used.append({"display_id": source.display_id, "reason": "; ".join(text.warnings) or "no text found"})
        else:
            readable.append(source)

    pages_by_key: dict[tuple[str, str], list[tuple[int | None, str]]] = {}
    keys = list({s.key for s in readable})
    if keys:
        for row in session.execute(select(ObjectPage.source_kind, ObjectPage.sha256, ObjectPage.page_number, ObjectPage.text)
                                   .where(tuple_(ObjectPage.source_kind, ObjectPage.sha256).in_(keys))
                                   .order_by(ObjectPage.source_kind, ObjectPage.sha256, ObjectPage.page_index)):
            pages_by_key.setdefault((row.source_kind, row.sha256), []).append((row.page_number, row.text))
    for source in readable:
        found = events_from_pages(pages_by_key.get(source.key, []), None)
        for event in found:
            events.append({"date": event.event_date.isoformat(), "date_text": event.date_text, "description": event.description,
                           "kind": event.event_type, "method": "text", "page": event.page_number, "source": _source_ref(source)})
        used[source.display_id] = {**_source_ref(source), "events": len(found)}

    # Dates the records hold.
    exhibits = {s.item_id: s for s in sources if s.kind == TextSourceKind.EVIDENCE}
    if exhibits:
        for item in session.scalars(select(EvidenceItem).where(EvidenceItem.id.in_(list(exhibits)), EvidenceItem.collected_at.is_not(None))):
            who = f" by {item.collected_by}" if item.collected_by else ""
            where = f" from {item.source}" if item.source else ""
            source = exhibits[item.id]
            events.append({"date": _local_date(item.collected_at, item.collected_tz).isoformat(), "date_text": None,
                           "description": f"{item.display_id} collected{who}{where}: {item.title}", "kind": "evidence_collected",
                           "method": "record", "page": None, "source": _source_ref(source)})
            used.setdefault(source.display_id, {**_source_ref(source), "events": 0})["events"] += 1
    for ref in session.scalars(select(CaseOfficialReference).where(CaseOfficialReference.case_family_id == family.id,
                                                                     CaseOfficialReference.ref_date.is_not(None))):
        events.append({"date": ref.ref_date.isoformat(), "date_text": None, "description": f"{queries.reference_label(ref)} (official reference)",
                       "kind": "official_reference", "method": "record", "page": None,
                       "source": {"kind": "record", "display_id": "Official references", "title": "Official references of the case",
                                  "path": None, "version_number": None, "version_id": None, "item_id": None}})
    # When imported findings happened, as their source recorded it (phase CM-6).
    imported = {s.version_id: s for s in sources if s.kind == TextSourceKind.ARTIFACT and s.artifact_type == ArtifactType.IMPORT.value}
    if imported:
        for row in session.scalars(select(IntegrationImport).where(IntegrationImport.artifact_version_id.in_(list(imported)),
                                                                   IntegrationImport.observed_at.is_not(None))):
            source = imported[row.artifact_version_id]
            events.append({"date": _local_date(row.observed_at, row.observed_tz).isoformat(), "date_text": None,
                           "description": f"{source.display_id}: {source.title} ({contract.label(row.item_type).lower()})",
                           "kind": "imported_finding", "method": "record", "page": None, "source": _source_ref(source)})
            used.setdefault(source.display_id, {**_source_ref(source), "events": 0})["events"] += 1

    seen: set[tuple[str, str]] = set()
    unique = []
    for event in sorted(events, key=lambda e: (e["date"], e["method"] != "record", e["source"]["display_id"], e["page"] or 0)):
        if (event["date"], event["description"]) not in seen:
            seen.add((event["date"], event["description"]))
            unique.append(event)
    return unique[:MAX_EVENTS], sorted(used.values(), key=lambda u: u["display_id"]), not_used


def rebuild(session: Session, actor: User, family: CaseFamily, store: EvidenceStore, embedder: Embedder | None, *,
            message: str | None = None) -> dict:
    """Rebuild the timeline from the case as it stands: a new version of the timeline note, and a history entry."""
    family = engine._lock_family(session, family.id)
    found = rights(session, actor, family)
    require(found.add_files, "You can read this case but not add to it", found)
    used_sources = [s for s in sources(session, None, family, shared=True) if s.artifact_type not in NOT_USED_TYPES]
    index.prepare(session, store, embedder, used_sources, evidence_seconds=EVIDENCE_SECONDS)
    events, used, not_used = build_events(session, family, used_sources)
    if not events:
        raise Invalid("No dates were found in the documents and notes everyone on the case may see, so there is no timeline "
                      "to build yet" + (f" ({len(not_used)} document(s) couldn't be used: see the coverage)" if not_used else ""))

    based_on = history.last_entry(session, family.id).seq
    current = _timeline_artifact(session, family)
    content = {"title": TIMELINE_TITLE, "generated_by": "Case Intelligence", "based_on_entry": based_on,
               "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "method": METHOD, "shared_view": SHARED_NOTE,
               "events": events, "sources_used": used, "not_used": not_used}
    derived = [u["version_id"] for u in used if u.get("version_id")]
    note = f"Rebuilt from the case as it stood at entry {based_on}: {len(events)} dated entries from {len(used)} source(s)"
    if current is not None:
        if current.sealed:
            raise Invalid("The timeline is sealed. It can be rebuilt once it is unsealed.")
        previous = engine.latest_version(session, current)
        artifact, version = engine._new_version(session, family=family, folder=None, artifact=current, artifact_type=ArtifactType.TIMELINE,
                                                title=current.title, content=content, author=actor, change_note=note,
                                                derived_from=[str(previous.id), *derived])
    else:
        folder = engine.ensure_folder(session, family, actor, FOLDER, system=True)
        artifact, version = engine._new_version(session, family=family, folder=folder, artifact=None, artifact_type=ArtifactType.TIMELINE,
                                                title=TIMELINE_TITLE, content=content, author=actor, change_note=note, derived_from=derived)
    text = (message or "").strip() or f"Timeline rebuilt: {len(events)} dated entries from {len(used)} source(s) (Case Intelligence)"
    entry = history.append(session, family, actor, HistoryKind.TIMELINE_GENERATED, text[:500], subject_type="artifact", subject_id=artifact.id,
                           details={"display_id": artifact.display_id, "version": version.version_number, "events": len(events),
                                    "sources": len(used), "based_on_entry": based_on, "content_sha256": version.content_sha256})
    return {"entry": entry, "artifact": artifact, "version": version, "events": len(events), "sources": len(used), "not_used": not_used}


def _timeline_artifact(session: Session, family: CaseFamily) -> Artifact | None:
    return session.scalar(select(Artifact).where(Artifact.case_family_id == family.id, Artifact.artifact_type == ArtifactType.TIMELINE.value,
                                                 Artifact.title == TIMELINE_TITLE, Artifact.status == FileStatus.ACTIVE.value))


def timeline_of(session: Session, viewer: User, family: CaseFamily) -> dict | None:
    """The timeline as it stands (None if there is none, or the viewer may not see it)."""
    artifact = _timeline_artifact(session, family)
    if artifact is None or artifact.id in hidden_file_ids(session, viewer, family):
        return None
    version = engine.latest_version(session, artifact)
    versions = session.scalar(select(func.count()).select_from(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact.id))
    who = queries.people(session, [version.author_id])
    content = version.content or {}
    folder = session.get(CaseFolder, artifact.folder_id)
    return {"folder": folder.name, "artifact_id": artifact.id, "display_id": artifact.display_id, "version_number": version.version_number,
            "versions": versions, "created_at": version.created_at, "author": who.get(version.author_id),
            "based_on_entry": content.get("based_on_entry"), "method": content.get("method"),
            "shared_view": content.get("shared_view"), "events": content.get("events", []),
            "sources_used": content.get("sources_used", []), "not_used": content.get("not_used", [])}
