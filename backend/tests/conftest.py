"""Shared test setup.

Tests use a separate database, `casesdb_test`, in the same PostgreSQL container,
so running tests can never change or delete your development data.
"""

import os

# Must run before anything imports `app`: settings are read once and cached.
os.environ["POSTGRES_DB"] = "casesdb_test"
os.environ["PRELOAD_MODELS"] = "false"  # tests use FakeEmbedder; don't load PyTorch in the background
os.environ["JWT_SECRET"] = "test-only-jwt-secret-0123456789abcdefghijklmnop"
os.environ["AUDIT_SECRET"] = "test-only-audit-secret-0123456789abcdefghijklm"
TEST_PASSWORD = "correct horse battery staple"

import math  # noqa: E402
import re  # noqa: E402
import zlib  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.models import EMBEDDING_DIM  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.schemas.case_record import CaseRecord  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


class FakeEmbedder:
    """Stand-in for the real model: each word (first 6 letters) adds to one of 384 slots.

    Texts sharing words get similar vectors, so tests can check the search plumbing
    (SQL, fusion, filters, access control) quickly and deterministically, without PyTorch.
    It understands no meaning: the real model has its own test (test_embeddings_real_model.py).
    """

    model_name = "test-word-hashing"
    min_similarity = 0.2
    min_passage_similarity = 0.5
    IGNORED = {"the", "a", "an", "of", "and", "or", "to", "was", "is", "by", "in", "on", "for", "had", "been"}

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        vector[0] = 0.05  # never all zeros (cosine is undefined for a zero vector)
        for word in re.findall(r"[a-z]+", text.lower()):
            if word not in self.IGNORED:
                vector[1 + zlib.crc32(word[:6].encode()) % (EMBEDDING_DIM - 1)] += 1.0
        norm = math.sqrt(sum(x * x for x in vector))
        return [x / norm for x in vector]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture(scope="session")
def alembic_cfg() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


def _create_test_database_if_missing() -> None:
    settings = get_settings()
    # Safety net: never run destructive test steps against a real database.
    assert settings.postgres_db.endswith("_test"), f"Refusing to test against '{settings.postgres_db}'"

    admin = create_engine(settings.database_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": settings.postgres_db}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{settings.postgres_db}"'))
    except OperationalError as exc:
        pytest.fail(
            f"Cannot reach PostgreSQL ({type(exc.orig).__name__}). "
            "Is it running? From the project root run: docker compose up -d",
            pytrace=False,
        )
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def migrated_db(alembic_cfg):
    """The test database with every migration applied."""
    _create_test_database_if_missing()
    command.upgrade(alembic_cfg, "head")


@pytest.fixture
def db_session(migrated_db):
    """A database session whose changes are rolled back after each test."""
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def build_pdf(pages: list[list[str] | None]) -> bytes:
    """A minimal, valid PDF. Each page is a list of text lines, or None for an image-only page
    (which looks like a scanned page: an image and no text)."""
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        4: b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray "
        b"/BitsPerComponent 8 /Length 1 >>\nstream\n\x00\nendstream",
    }
    kids = []
    number = 5
    for lines in pages:
        if lines is None:
            content = b"q 300 0 0 400 100 200 cm /Im1 Do Q"
        else:
            escaped = (line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines)
            content = ("BT /F1 11 Tf 14 TL 72 760 Td\n" + "\n".join(f"({e}) Tj T*" for e in escaped) + "\nET").encode(
                "latin-1"
            )
        objects[number] = b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"
        objects[number + 1] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {number} 0 R "
            "/Resources << /Font << /F1 3 0 R >> /XObject << /Im1 4 0 R >> >> >>"
        ).encode()
        kids.append(f"{number + 1} 0 R")
        number += 2
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode()

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for num in sorted(objects):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(out)


@pytest.fixture
def make_pdf(tmp_path):
    """Write a PDF under tmp_path. Returns its path."""

    def _make(relative_path: str, pages: list[list[str] | None]) -> Path:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(build_pdf(pages))
        return path

    return _make


@pytest.fixture
def make_user(db_session):
    """Create a user in the test's session (password: TEST_PASSWORD)."""
    from app.auth.users import create_user
    from app.core.enums import Role, Sensitivity

    def _make(username: str, role: str = "analyst", clearance: str = "public"):
        return create_user(db_session, username, username.title(), TEST_PASSWORD, Role(role), Sensitivity(clearance))

    return _make


def auth_header(user) -> dict[str, str]:
    from app.auth.tokens import create_access_token

    token, _ = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def app_overrides(db_session, fake_embedder):
    """Point the app at the test's session (data and audit rows roll back) and the fake model."""
    from app.audit.log import AuditLog, get_audit_log
    from app.auth.ratelimit import FailedLoginLimiter, get_login_limiter
    from app.db.session import get_db
    from app.embeddings.model import get_embedder
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    app.dependency_overrides[get_audit_log] = lambda: AuditLog(client_ip="testclient", session=db_session)
    # A fresh login limiter per test: every test client logs in from the same address ("testclient").
    limiter = FailedLoginLimiter(limit=20, window_seconds=900)
    app.dependency_overrides[get_login_limiter] = lambda: limiter
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def anonymous_api(app_overrides):
    """A client that is not logged in."""
    from fastapi.testclient import TestClient

    with TestClient(app_overrides) as client:
        yield client


@pytest.fixture
def client_as(app_overrides, make_user):
    """client_as("name", role=..., clearance=...) -> a client logged in as a new user (.user)."""
    from fastapi.testclient import TestClient

    clients = []

    def _client(username: str, role: str = "analyst", clearance: str = "public"):
        user = make_user(username, role, clearance)
        client = TestClient(app_overrides, headers=auth_header(user))
        client.__enter__()
        client.user = user
        clients.append(client)
        return client

    yield _client
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def api(client_as):
    """The default test client: an analyst with public clearance."""
    return client_as("test.analyst")


@pytest.fixture
def add_case(db_session, make_record, fake_embedder):
    """Create case TEST-API-<n> with one document whose chunks are `passages` (one per page),
    embedded with FakeEmbedder."""
    from app.db.models import DocumentChunk
    from app.ingestion.store import upsert_case_record

    def _add(n, *, title, year, outcome=None, sensitivity="public", passages=(), source_system="test_source"):
        record = make_record(
            source_system=source_system,
            source_record_id=f"API-{n}",
            display_id=f"TEST-API-{n}",
            title=title,
            sensitivity=sensitivity,
            outcome={"text": outcome, "source_field": "disposal_nature"} if outcome else None,
            dates=[{"kind": "decision", "value": f"{year}-06-01", "source_field": "decision_date"}],
            documents=[
                {"doc_type": "judgment", "source_uri": f"https://example.org/{n}.pdf", "local_path": f"raw/test/{n}.pdf"}
            ],
        )
        case, _ = upsert_case_record(db_session, record)
        document = case.documents[0]
        for i, text in enumerate(passages):
            db_session.add(
                DocumentChunk(
                    document_id=document.id,
                    case_id=case.id,
                    chunk_index=i,
                    page_start=i + 1,
                    page_end=i + 1,
                    text=text,
                    word_count=len(text.split()),
                    embedding=fake_embedder.embed_query(text),
                    embedding_model=fake_embedder.model_name,
                )
            )
        db_session.flush()
        return case

    return _add


@pytest.fixture
def make_record():
    """Build a valid CaseRecord: the minimum required fields plus any overrides."""

    def _make(**overrides) -> CaseRecord:
        data = {
            "source_system": "test_source",
            "source_record_id": "TEST-001",
            "display_id": "TEST-001",
            "sensitivity": "public",
            "provenance": {
                "connector": "test_connector",
                "connector_version": "0.0.1",
                "retrieved_at": "2026-11-03T10:00:00Z",
            },
        }
        data.update(overrides)
        return CaseRecord.model_validate(data)

    return _make
