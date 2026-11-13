"""Case Intelligence inside cases: the endpoints (docs/case-management/06, 13).

Each works on one case and only on what the user may see in it (scope.py). As everywhere in the module: anything not visible answers
404, every request is audited (searches and questions by a keyed fingerprint only, never their text), nothing is deleted.
Reading requests first index what the case's files still lack (notes always, documents for a few seconds); POST .../prepare reads
the rest.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.audit.log import fingerprint
from app.auth.access import AccessContext
from app.auth.dependencies import CurrentUser, get_access_context
from app.casemgmt import history
from app.casemgmt import schemas as s
from app.casemgmt.access import get_family
from app.casemgmt.api import Audit, Audited, DbSession, IdempotencyKeyHeader
from app.casemgmt.idempotency import Once
from app.casemgmt.intelligence import assistant, index, offences, scope, search, similar, timeline
from app.casemgmt.models import CaseFamily
from app.casemgmt.storage import EvidenceStore, get_evidence_store
from app.chat.llm import ChatModel, ChatModelUnavailable, get_chat_model
from app.db.models import User
from app.embeddings.model import Embedder, get_embedder

router = APIRouter(prefix="/v1", tags=["case management: case intelligence"])

Access = Annotated[AccessContext, Depends(get_access_context)]
OptionalEmbedder = Annotated[Embedder | None, Depends(get_embedder)]
Store = Annotated[EvidenceStore, Depends(get_evidence_store)]
QUICK_SECONDS = 10  # documents read while answering a reading request
PREPARE_SECONDS = 90  # documents read by an explicit "prepare"


def _case(db: Session, user: User, case_id: uuid.UUID) -> tuple[CaseFamily, list]:
    family = get_family(db, user, case_id)
    return family, scope.sources(db, user, family)


@router.get("/cases/{case_id}/intelligence", response_model=s.IntelligenceStatus)
def status_of(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit, store: Store, embedder: OptionalEmbedder) -> dict:
    """What of this case Case Intelligence has read: documents, notes, passages, and what is missing and why.

    Notes are read on the way (they are small); documents only by the other requests and by prepare."""
    with Audited(db, audit, user, "cm.intelligence.status", "cm_case", case_id) as event:
        family, sources = _case(db, user, case_id)
        event.target_id = family.display_id
        coverage = index.ensure_indexed(db, store, embedder, sources, evidence_seconds=0)
        result = {"coverage": coverage.as_dict()}
        event.read()
    return result


@router.post("/cases/{case_id}/intelligence/prepare", response_model=s.IntelligenceStatus)
def prepare(case_id: uuid.UUID, body: s.PrepareRequest, user: CurrentUser, db: DbSession, audit: Audit, store: Store,
            embedder: OptionalEmbedder) -> dict:
    """Read the documents and notes of this case that haven't been read yet (each file once, whatever case holds it)."""
    with Audited(db, audit, user, "cm.intelligence.prepare", "cm_case", case_id) as event:
        family, sources = _case(db, user, case_id)
        event.target_id = family.display_id
        coverage = index.ensure_indexed(db, store, embedder, sources, evidence_seconds=PREPARE_SECONDS)
        result = {"coverage": coverage.as_dict()}
        event.write(indexed=coverage.indexed, pending=len(coverage.pending))
    return result


@router.post("/cases/{case_id}/intelligence/search", response_model=s.CaseSearchResponse)
def search_inside(case_id: uuid.UUID, body: s.CaseSearchRequest, user: CurrentUser, db: DbSession, audit: Audit, store: Store,
                  embedder: OptionalEmbedder) -> dict:
    """Search the documents and notes of this case (POST: the words stay out of URLs)."""
    asked = {"query_fingerprint": fingerprint(body.query), "query_length": len(body.query), "mode": body.mode}
    with Audited(db, audit, user, "cm.intelligence.search", "cm_case", case_id, **asked) as event:
        family, sources = _case(db, user, case_id)
        event.target_id = family.display_id
        coverage = index.ensure_indexed(db, store, embedder, sources, evidence_seconds=QUICK_SECONDS)
        found = search.search_case(db, embedder, sources, body.query, body.mode, body.limit)
        result = {"query": body.query, "coverage": coverage.as_dict(), **found}
        event.read(sources=found["total_sources"], passages=found["total_passages"])
    return result


@router.get("/cases/{case_id}/intelligence/similar", response_model=s.CaseSimilarResponse)
def similar_cases(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit, access: Access, store: Store,
                  embedder: OptionalEmbedder,
                  scope_: Annotated[Literal["all", "investigations", "knowledge_base"], Query(alias="scope")] = "all",
                  limit: Annotated[int, Query(ge=1, le=50)] = 10, offset: Annotated[int, Query(ge=0, le=200)] = 0) -> dict:
    """Past cases (knowledge base) and other investigations similar to this one, with why."""
    with Audited(db, audit, user, "cm.intelligence.similar", "cm_case", case_id, scope=scope_) as event:
        family, sources = _case(db, user, case_id)
        event.target_id = family.display_id
        coverage = index.ensure_indexed(db, store, embedder, sources, evidence_seconds=QUICK_SECONDS)
        found = similar.similar_for_case(db, user, access, embedder, store, family, sources, scope=scope_, limit=limit, offset=offset)
        result = {"coverage": coverage.as_dict(), **found}
        event.read(investigations=found["investigations_total"], knowledge_base=found["knowledge_total"])
    return result


@router.post("/cases/{case_id}/intelligence/ask", response_model=s.CaseAnswer)
def ask(case_id: uuid.UUID, body: s.AskRequest, user: CurrentUser, db: DbSession, audit: Audit, store: Store,
        embedder: OptionalEmbedder, model: Annotated[ChatModel, Depends(get_chat_model)]) -> dict:
    """Ask about the case. Answers cite exhibit or note, version and page."""
    asked = {"question_fingerprint": fingerprint(body.question), "question_length": len(body.question)}
    failure: ChatModelUnavailable | None = None
    with Audited(db, audit, user, "cm.intelligence.ask", "cm_case", case_id, **asked) as event:
        family, sources = _case(db, user, case_id)
        event.target_id = family.display_id
        coverage = index.ensure_indexed(db, store, embedder, sources, evidence_seconds=QUICK_SECONDS)
        try:
            answered = assistant.answer(db, model, embedder, family, sources, body.question, body.history)
        except ChatModelUnavailable as exc:
            failure = exc
            event.error(reason=str(exc), cause=type(exc.__cause__).__name__ if exc.__cause__ else None)
        else:
            result = {**answered, "coverage": coverage.as_dict()}
            event.read(sources=len(answered["sources"]), answered=answered["answered"],
                       cited=sum(1 for x in answered["sources"] if x["cited"]), model=answered["model"], seconds=answered["seconds"])
    if failure is not None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(failure)) from failure
    return result


@router.get("/cases/{case_id}/intelligence/offences", response_model=s.OffenceSuggestions)
def offence_sections(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit, access: Access, store: Store,
                     embedder: OptionalEmbedder) -> dict:
    """Sections cited in this case's documents and notes, and sections cited by the most similar past cases (prompts only)."""
    with Audited(db, audit, user, "cm.intelligence.offences", "cm_case", case_id) as event:
        family, sources = _case(db, user, case_id)
        event.target_id = family.display_id
        coverage = index.ensure_indexed(db, store, embedder, sources, evidence_seconds=QUICK_SECONDS)
        cited = offences.cited_here(db, sources)
        doc = similar.query_document(db, family, sources, embedder).doc
        suggested, considered, notices = offences.from_similar_cases(db, access, embedder, doc, {c["key"] for c in cited})
        result = {"cited_here": cited, "from_similar_cases": suggested, "similar_cases_considered": considered, "notices": notices,
                  "disclaimer": offences.DISCLAIMER, "coverage": coverage.as_dict()}
        event.read(cited=len(cited), suggested=len(suggested))
    return result


@router.get("/cases/{case_id}/intelligence/timeline", response_model=s.TimelineView)
def timeline_view(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """The reconstructed timeline (if one was built and you may see it)."""
    with Audited(db, audit, user, "cm.intelligence.timeline_read", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        found = timeline.timeline_of(db, user, family)
        result = {"timeline": found}
        event.read(version=found["version_number"] if found else None)
    return result


@router.post("/cases/{case_id}/intelligence/timeline", response_model=s.TimelineRebuilt, status_code=status.HTTP_201_CREATED)
def rebuild_timeline(case_id: uuid.UUID, body: s.TimelineRebuild, user: CurrentUser, db: DbSession, audit: Audit, store: Store,
                     embedder: OptionalEmbedder, idempotency_key: IdempotencyKeyHeader = None):
    """Rebuild the timeline from the case as it stands: a new version of the timeline note."""
    with Audited(db, audit, user, "cm.intelligence.timeline", "cm_case", case_id) as event:
        once = Once(db, user, idempotency_key, f"POST /api/v1/cases/{case_id}/intelligence/timeline", body.model_dump(mode="json"))
        if (previous := once.previous()) is not None:
            event.read(replayed=True)
            return previous
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        built = timeline.rebuild(db, user, family, store, embedder, message=body.message)
        result = {"entry": built["entry"].seq, "artifact_id": built["artifact"].id, "display_id": built["artifact"].display_id,
                  "version_number": built["version"].version_number, "events": built["events"], "sources": built["sources"],
                  "not_used": built["not_used"]}
        once.save(status.HTTP_201_CREATED, s.TimelineRebuilt, result)
        event.write(entry=built["entry"].seq, events=built["events"], sources=built["sources"], version=built["version"].version_number)
    return result
