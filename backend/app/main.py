"""FastAPI application entry point.

Run locally (from the backend folder):
    uv run uvicorn app.main:app --reload --port 8000
"""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.cases import router as cases_router
from app.api.health import router as health_router
from app.api.search import router as search_router
from app.api.uploads import router as uploads_router
from app.casemgmt.api import router as case_management_router
from app.casemgmt.errors import CaseManagementError
from app.casemgmt.chat_api import router as chat_router
from app.casemgmt.collab_api import router as collaboration_router
from app.casemgmt.evidence_api import router as evidence_router
from app.casemgmt.intelligence.api import router as intelligence_router
from app.casemgmt.governance.api import router as governance_router
from app.casemgmt.integrations.api import router as integrations_router
from app.casemgmt.workspace_api import router as workspace_router
from app.casemgmt.dashboards_api import router as dashboards_router
from app.casemgmt.people_api import router as people_router
from app.cdr.api import router as cdr_router
from app.core.config import get_settings
from app.core.headers import ApiResponseHeaders
from app.embeddings.model import get_embedder


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if get_settings().preload_models:
        # In the background, so the API starts answering (e.g. keyword search) immediately.
        threading.Thread(target=get_embedder, name="preload-embedder", daemon=True).start()
    yield


async def case_management_error(_request: Request, exc: CaseManagementError) -> JSONResponse:
    """404 / 403 / 409 / 422 from the Case Management module. `exists` is for the audit log only."""
    body = {"detail": str(exc), **{key: value for key, value in exc.extra.items() if key != "exists"}}
    return JSONResponse(status_code=exc.status, content=jsonable_encoder(body))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        # The interactive docs list every endpoint: only offered in development.
        docs_url="/docs" if settings.show_api_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.show_api_docs else None,
    )
    app.add_middleware(ApiResponseHeaders)
    # All API routes live under /api so the frontend can proxy them in one place.
    # /api/health and /api/auth/token are the only routes that work without logging in.
    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(audit_router, prefix="/api")
    app.include_router(cases_router, prefix="/api")
    app.include_router(search_router, prefix="/api")
    app.include_router(uploads_router, prefix="/api")
    # Case Management (docs/case-management/): everything under /api/v1.
    app.add_exception_handler(CaseManagementError, case_management_error)
    # Evidence and collaboration routes first: the module's main router ends with catch-alls that refuse deletions (405).
    app.include_router(evidence_router, prefix="/api")
    app.include_router(collaboration_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(workspace_router, prefix="/api")
    app.include_router(people_router, prefix="/api")
    app.include_router(dashboards_router, prefix="/api")
    app.include_router(intelligence_router, prefix="/api")
    app.include_router(integrations_router, prefix="/api")
    app.include_router(governance_router, prefix="/api")
    app.include_router(cdr_router, prefix="/api")
    app.include_router(case_management_router, prefix="/api")
    return app


app = create_app()
