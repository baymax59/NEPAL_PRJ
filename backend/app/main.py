"""FastAPI application entry point.

Run locally (from the backend folder):
    uv run uvicorn app.main:app --reload --port 8000
"""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.cases import router as cases_router
from app.api.cdr_proxy import router as cdr_proxy_router
from app.api.cdr_session import router as cdr_router
from app.api.health import router as health_router
from app.api.search import router as search_router
from app.api.uploads import router as uploads_router
from app.core.config import get_settings
from app.core.headers import ApiResponseHeaders
from app.embeddings.model import get_embedder


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if get_settings().preload_models:
        # In the background, so the API starts answering (e.g. keyword search) immediately.
        threading.Thread(target=get_embedder, name="preload-embedder", daemon=True).start()
    yield


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
    app.include_router(cdr_router, prefix="/api")
    app.include_router(cdr_proxy_router, prefix="/api")
    return app


app = create_app()
