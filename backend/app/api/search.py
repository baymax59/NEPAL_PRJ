"""Search endpoint: hybrid keyword + semantic search, for logged-in users."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit.log import AuditLog, fingerprint, get_audit_log
from app.auth.access import AccessContext
from app.auth.dependencies import CurrentUser, get_access_context
from app.core.enums import AuditOutcome
from app.db.session import get_db
from app.embeddings.model import Embedder, get_embedder
from app.schemas.search import SearchRequest, SearchResponse
from app.search.hybrid import search

router = APIRouter(tags=["search"])


# POST, not GET: the query text (which may describe sensitive facts) then travels in the
# request body instead of the URL, where it would end up in server and proxy logs.
@router.post("/search", response_model=SearchResponse)
def search_endpoint(
    request: SearchRequest,
    db: Annotated[Session, Depends(get_db)],
    access: Annotated[AccessContext, Depends(get_access_context)],
    user: CurrentUser,
    audit: Annotated[AuditLog, Depends(get_audit_log)],
    embedder: Annotated[Embedder | None, Depends(get_embedder)],
) -> SearchResponse:
    response = search(db, access, embedder, request)
    audit.record(
        "search",
        AuditOutcome.SUCCESS,
        user=user,
        details={
            # The search text itself is never stored: only a keyed fingerprint and its length.
            "query_fingerprint": fingerprint(request.query),
            "query_length": len(request.query),
            "mode": response.mode,
            "filters": request.filters.model_dump(exclude_defaults=True),
            "total": response.total_cases,
        },
    )
    return response
