"""Who sees which cases (clearance + grants) and who may do what (roles, upload ownership)."""

import datetime as dt

import pytest

from app.db.models import CaseAccessGrant

PASSAGE = "Anticipatory bail was refused by the High Court and the appellant appealed."


@pytest.fixture
def cases(add_case):
    """One case at each sensitivity level, all with the same text so every search finds all."""
    return {
        level: add_case(n, title=f"{level} case", year=2023, sensitivity=level, passages=[PASSAGE])
        for n, level in enumerate(["public", "internal", "restricted", "confidential"], start=1)
    }


def listed(client) -> list[str]:
    return sorted(item["title"] for item in client.get("/api/cases").json()["items"])


def searched(client) -> list[str]:
    response = client.post("/api/search", json={"query": "anticipatory bail refused"})
    return sorted(hit["case"]["title"] for hit in response.json()["results"])


def test_clearance_decides_which_cases_are_listed_and_searchable(client_as, cases):
    public_user = client_as("pat", clearance="public")
    restricted_user = client_as("rita", clearance="restricted")

    assert listed(public_user) == searched(public_user) == ["public case"]
    assert listed(restricted_user) == searched(restricted_user) == ["internal case", "public case", "restricted case"]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/cases/TEST-API-3", None),
        ("post", "/api/cases/TEST-API-3/explain", {"query": "bail"}),
        ("get", "/api/cases/TEST-API-3/similar", None),
    ],
)
def test_a_case_above_clearance_looks_like_it_does_not_exist(client_as, cases, method, path, body):
    client = client_as("pat", clearance="public")
    kwargs = {"json": body} if body else {}

    response = getattr(client, method)(path, **kwargs)
    missing = getattr(client, method)(path.replace("TEST-API-3", "TEST-API-999"), **kwargs)

    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()


def test_similar_cases_never_include_cases_above_clearance(client_as, cases):
    public_user = client_as("pat", clearance="public")
    restricted_user = client_as("rita", clearance="restricted")

    def similar(client) -> list[str]:
        return sorted(r["case"]["title"] for r in client.get("/api/cases/TEST-API-1/similar").json()["results"])

    # All four cases have identical text, so only access control can explain the difference.
    assert similar(public_user) == []
    assert similar(restricted_user) == ["internal case", "restricted case"]


def test_a_grant_opens_exactly_one_case(client_as, cases, db_session):
    client = client_as("pat", clearance="public")
    db_session.add(CaseAccessGrant(case_id=cases["restricted"].id, user_id=client.user.id, reason="assigned", granted_by="admin"))
    db_session.flush()

    assert client.get("/api/cases/TEST-API-3").status_code == 200
    assert client.get("/api/cases/TEST-API-4").status_code == 404  # confidential: no grant
    assert listed(client) == ["public case", "restricted case"]


def test_an_expired_grant_opens_nothing(client_as, cases, db_session):
    client = client_as("pat", clearance="public")
    db_session.add(
        CaseAccessGrant(
            case_id=cases["restricted"].id,
            user_id=client.user.id,
            reason="assigned",
            granted_by="admin",
            expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(days=1),
        )
    )
    db_session.flush()

    assert client.get("/api/cases/TEST-API-3").status_code == 404


def test_the_admin_role_does_not_bypass_clearance(client_as, cases):
    admin = client_as("root", role="admin", clearance="public")

    assert listed(admin) == ["public case"]


def test_viewers_cannot_upload(client_as):
    viewer = client_as("vera", role="viewer")

    response = viewer.post("/api/uploads", files={"file": ("case.txt", b"Some case text.", "text/plain")})

    assert response.status_code == 403


def test_uploads_are_private_to_their_owner(client_as, tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    owner = client_as("olga")
    other = client_as("oscar")
    upload_id = owner.post("/api/uploads", files={"file": ("c.txt", b"Anticipatory bail refused.", "text/plain")}).json()["id"]

    assert other.get(f"/api/uploads/{upload_id}").status_code == 404
    assert other.post(f"/api/uploads/{upload_id}/similar", json={}).status_code == 404
    assert other.delete(f"/api/uploads/{upload_id}").status_code == 404
    assert owner.get(f"/api/uploads/{upload_id}").status_code == 200  # still there
