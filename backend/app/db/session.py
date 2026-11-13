"""Database engine and per-request sessions."""

from collections.abc import Callable, Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# pool_pre_ping checks a pooled connection is still alive before using it,
# so a database restart doesn't cause errors on the next request.
# The application's own login (role cm_runtime) when configured: it can't delete case records (CM-7).
engine = create_engine(get_settings().runtime_database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    with SessionLocal() as session:
        yield session


def get_session_factory() -> Callable[[], Session]:
    """FastAPI dependency for long-lived responses (the live notification stream).

    Such a response opens a short session each time it needs the database (`with factory() as session:`) instead
    of holding one connection for as long as the browser stays connected.
    """
    return SessionLocal
