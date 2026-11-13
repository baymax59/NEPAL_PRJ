"""Helpers for the Case Management tests. All names, numbers and facts are fictional."""

from sqlalchemy import func, select

from app.casemgmt.models import Organization, PoliceStation, UserStation

CASE = {
    "title": "Online banking fraud investigation (FICTIONAL TEST CASE)",
    "case_type": "cyber_fraud",
    "description": "Fictional: a complainant reports three unauthorised transfers, INR 250000 in total.",
    "priority": "high",
    "classification": "restricted",
    "jurisdiction": "Example Nagar PS (fictional)",
}


def create_case(client, **overrides) -> dict:
    response = client.post("/api/v1/cases", json={**CASE, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def case(client, case_id, status: int = 200) -> dict:
    response = client.get(f"/api/v1/cases/{case_id}")
    assert response.status_code == status, response.text
    return response.json()


def folders(client, case_id) -> list[dict]:
    response = client.get(f"/api/v1/cases/{case_id}/folders")
    assert response.status_code == 200, response.text
    return response.json()


def files(client, case_id, folder: str | None = None, include_withdrawn: bool = False, status: int = 200) -> list[dict]:
    params = {"include_withdrawn": "true"} if include_withdrawn else {}
    if folder:
        params["folder"] = folder
    response = client.get(f"/api/v1/cases/{case_id}/files", params=params)
    assert response.status_code == status, response.text
    return response.json()["files"] if status == 200 else response.json()


def add_note(client, case_id, folder: str = "investigation-notes", title: str = "A note (fictional)",
             text: str = "Fictional text of a note.", artifact_type: str = "note", status: int = 201, **fields) -> dict:
    body = {"folder": folder, "artifact_type": artifact_type, "title": title, "content": {"text": text}, **fields}
    response = client.post(f"/api/v1/cases/{case_id}/notes", json=body)
    assert response.status_code == status, response.text
    return response.json()


def revise(client, artifact_id, text: str, expected_version: int, status: int = 201, **fields) -> dict:
    response = client.post(f"/api/v1/artifacts/{artifact_id}/versions",
                           json={"content": {"text": text}, "expected_version": expected_version, **fields})
    assert response.status_code == status, response.text
    return response.json()


def withdraw(client, kind_path: str, item_id, reason: str = "Entered by mistake (fictional)", status: int = 200) -> dict:
    """kind_path: 'artifacts' or 'evidence'."""
    response = client.post(f"/api/v1/{kind_path}/{item_id}/withdraw", json={"reason": reason})
    assert response.status_code == status, response.text
    return response.json()


def history(client, case_id, status: int = 200) -> list[dict]:
    response = client.get(f"/api/v1/cases/{case_id}/history", params={"limit": 500})
    assert response.status_code == status, response.text
    return response.json()["entries"] if status == 200 else response.json()


def set_status(client, case_id, value: str, field: str = "workflow", reason: str = "Fictional test transition", status: int = 200) -> dict:
    response = client.post(f"/api/v1/cases/{case_id}/status", json={"field": field, "value": value, "reason": reason})
    assert response.status_code == status, response.text
    return response.json()


# ---------------------------------------------------------------- the team


def add_member(client, case_id, user, role: str = "sub_investigator", status: int = 201) -> dict:
    response = client.post(f"/api/v1/cases/{case_id}/team", json={"user_id": str(user.id), "role": role})
    assert response.status_code == status, response.text
    return response.json()


def remove_member(client, case_id, user, status: int = 200, reason: str = "No longer on this case (fictional)") -> dict:
    response = client.post(f"/api/v1/cases/{case_id}/team/{user.id}/remove", json={"reason": reason})
    assert response.status_code == status, response.text
    return response.json()


def team_of(client, case_id) -> list[dict]:
    response = client.get(f"/api/v1/cases/{case_id}/team")
    assert response.status_code == 200, response.text
    return response.json()["team"]


# ---------------------------------------------------------------- evidence

PNG = b"\x89PNG\r\n\x1a\n" + b"FICTIONAL TEST IMAGE: a WhatsApp message asking for an OTP"


def upload(client, case_id, content: bytes, filename: str = "whatsapp-message.png", *, folder: str = "digital-evidence",
           title: str = "WhatsApp message (fictional)", status: int = 201, **fields) -> dict:
    """Add an exhibit through the API (multipart form), into a folder of the case."""
    data = {"folder": folder, "title": title, **fields}
    response = client.post(f"/api/v1/cases/{case_id}/evidence", data=data, files={"file": (filename, content, "application/octet-stream")})
    assert response.status_code == status, response.text
    return response.json()


def stored_files(store) -> list:
    """Every object file in a test evidence store."""
    objects = store.root / "objects"
    return [p for p in objects.rglob("*") if p.is_file()] if objects.exists() else []


def waiting_files(store) -> list:
    """Uploads received but neither accepted nor refused (there should never be any after a request)."""
    incoming = store.root / "incoming"
    return list(incoming.iterdir()) if incoming.exists() else []


# ---------------------------------------------------------------- tasks and notices


def notices(client) -> list[str]:
    return [n["kind"] for n in client.get("/api/v1/notifications").json()["items"]]


# ---------------------------------------------------------------- police stations


def make_station(db_session, code: str) -> PoliceStation:
    org = db_session.scalars(select(Organization).order_by(Organization.created_at)).first()
    station = PoliceStation(organization_id=org.id, code=code, name=f"{code} police station (fictional)")
    db_session.add(station)
    db_session.commit()
    return station


def place(db_session, user, *stations) -> None:
    """Move a user to exactly these stations (ending the old assignments, never deleting them)."""
    for row in db_session.scalars(select(UserStation).where(UserStation.user_id == user.id, UserStation.revoked_at.is_(None))):
        row.revoked_at = func.now()
    for station in stations:
        db_session.add(UserStation(user_id=user.id, station_id=station.id))
    db_session.commit()
