import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health_reports_database_and_pgvector(client, migrated_db):
    """Integration test: needs the database running (docker compose up -d)."""
    response = client.get("/api/health")

    assert response.status_code == 200, (
        f"Got {response.status_code}: {response.text}. Is the database running? Try: docker compose up -d"
    )
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["pgvector"], "pgvector extension is not enabled in the database"


def test_health_returns_503_without_leaking_details_when_database_is_down(client):
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("password authentication failed for user caseuser"))

    app.dependency_overrides[get_db] = lambda: BrokenSession()

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable", "pgvector": None}
    assert "password" not in response.text
