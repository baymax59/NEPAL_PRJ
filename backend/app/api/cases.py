"""Case list, filter options, case details, explanations and similar cases.

All require a logged-in user; what each user sees depends on their clearance and grants.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.audit.log import AuditLog, fingerprint, get_audit_log
from app.auth.access import AccessContext
from app.auth.dependencies import CurrentUser, get_access_context
from app.cases.queries import case_exists, filter_options, get_case_detail, get_visible_case, list_cases
from app.chat.llm import ChatModel, ChatModelUnavailable, get_chat_model
from app.chat.service import answer_question
from app.schemas.chat import ChatAnswer, ChatRequest
from app.core.enums import AuditOutcome
from app.db.session import get_db
from app.embeddings.model import Embedder, get_embedder
from app.explain.service import explain_case
from app.schemas.case_record import DISPLAY_ID_PATTERN
from app.schemas.cases import CaseDetail, CaseList, CaseListParams, FilterOptions
from app.schemas.explain import ExplainRequest, MatchExplanation
from app.schemas.similar import SimilarCasesResponse, SimilarParams
from app.similar.service import document_from_case, find_similar_cases

router = APIRouter(prefix="/cases", tags=["cases"])

DbSession = Annotated[Session, Depends(get_db)]
Access = Annotated[AccessContext, Depends(get_access_context)]
Audit = Annotated[AuditLog, Depends(get_audit_log)]
OptionalEmbedder = Annotated[Embedder | None, Depends(get_embedder)]
DisplayId = Annotated[str, Path(pattern=DISPLAY_ID_PATTERN)]


def not_visible(db: Session, audit: AuditLog, action: str, user, display_id: str) -> HTTPException:
    """Record why the case wasn't shown, then give the user the same answer either way."""
    outcome = AuditOutcome.DENIED if case_exists(db, display_id) else AuditOutcome.NOT_FOUND
    audit.record(action, outcome, user=user, target_type="case", target_id=display_id)
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")


@router.get("", response_model=CaseList)
def list_cases_endpoint(
    params: Annotated[CaseListParams, Query()], db: DbSession, access: Access, user: CurrentUser, audit: Audit
) -> CaseList:
    result = list_cases(db, access, params)
    audit.record(
        "case.list", AuditOutcome.SUCCESS, user=user, details={**params.model_dump(exclude_defaults=True), "total": result.total}
    )
    return result


# Declared before /{display_id} so "filters" isn't taken for a case ID.
@router.get("/filters", response_model=FilterOptions)
def filter_options_endpoint(db: DbSession, access: Access) -> FilterOptions:
    return filter_options(db, access)


@router.get("/{display_id}", response_model=CaseDetail)
def case_detail_endpoint(display_id: DisplayId, db: DbSession, access: Access, user: CurrentUser, audit: Audit) -> CaseDetail:
    case = get_case_detail(db, access, display_id)
    if case is None:
        raise not_visible(db, audit, "case.view", user, display_id)
    audit.record("case.view", AuditOutcome.SUCCESS, user=user, target_type="case", target_id=display_id)
    return case


# POST so the query text stays out of URLs and logs, as with /api/search.
@router.post("/{display_id}/explain", response_model=MatchExplanation)
def explain_endpoint(
    display_id: DisplayId,
    request: ExplainRequest,
    db: DbSession,
    access: Access,
    user: CurrentUser,
    audit: Audit,
    embedder: OptionalEmbedder,
) -> MatchExplanation:
    case = get_visible_case(db, access, display_id)
    if case is None:
        raise not_visible(db, audit, "case.explain", user, display_id)
    audit.record(
        "case.explain",
        AuditOutcome.SUCCESS,
        user=user,
        target_type="case",
        target_id=display_id,
        details={"query_fingerprint": fingerprint(request.query), "query_length": len(request.query)},
    )
    return explain_case(db, case, embedder, request.query)


@router.post("/{display_id}/chat", response_model=ChatAnswer)
def chat_endpoint(
    display_id: DisplayId,
    request: ChatRequest,
    db: DbSession,
    access: Access,
    user: CurrentUser,
    audit: Audit,
    embedder: OptionalEmbedder,
    model: Annotated[ChatModel, Depends(get_chat_model)],
) -> ChatAnswer:
    """Ask about a case (optionally compared with another). Access is checked before anything is retrieved."""
    case = get_visible_case(db, access, display_id)
    if case is None:
        raise not_visible(db, audit, "case.chat", user, display_id)
    cases = [case]
    if request.compare_with:
        other = get_visible_case(db, access, request.compare_with)
        if other is None:
            raise not_visible(db, audit, "case.chat", user, request.compare_with)
        cases.append(other)

    details = {"question_fingerprint": fingerprint(request.question), "question_length": len(request.question)}
    try:
        result = answer_question(db, model, embedder, cases, request.question, request.history)
    except ChatModelUnavailable as exc:
        # "cause" is the technical error behind the message (e.g. ReadTimeout), for whoever investigates.
        cause = type(exc.__cause__).__name__ if exc.__cause__ else None
        audit.record(
            "case.chat",
            AuditOutcome.ERROR,
            user=user,
            target_type="case",
            target_id=display_id,
            details={**details, "reason": str(exc), "cause": cause},
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    audit.record(
        "case.chat",
        AuditOutcome.SUCCESS,
        user=user,
        target_type="case",
        target_id=display_id,
        details={
            **details,
            "compare_with": request.compare_with,
            "sources": len(result.sources),
            "cited": sum(s.cited for s in result.sources),
            "answered": result.answered,
            "model": result.model,
            "seconds": result.seconds,
        },
    )
    return result


@router.get("/{display_id}/similar", response_model=SimilarCasesResponse)
def similar_cases_endpoint(
    display_id: DisplayId,
    params: Annotated[SimilarParams, Query()],
    db: DbSession,
    access: Access,
    user: CurrentUser,
    audit: Audit,
    embedder: OptionalEmbedder,
) -> SimilarCasesResponse:
    """Historical cases similar to this one (the case itself is excluded)."""
    case = get_visible_case(db, access, display_id)
    if case is None:
        raise not_visible(db, audit, "case.similar", user, display_id)
    result = find_similar_cases(db, access, embedder, document_from_case(db, case), params, params.limit, params.offset)
    audit.record(
        "case.similar",
        AuditOutcome.SUCCESS,
        user=user,
        target_type="case",
        target_id=display_id,
        details={"total": result.total_cases},
    )
    return result
