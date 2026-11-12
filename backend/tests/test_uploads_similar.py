"""Uploading a new case (POST /api/uploads) and finding similar historical cases."""

import io

import docx
import pytest

from app.core.config import get_settings
from app.embeddings.model import get_embedder
from app.explain.indexing import store_provisions
from app.main import app
from conftest import build_pdf

BAIL = [
    "The appellant sought anticipatory bail under Section 438 of the Code of Criminal Procedure.",
    "Anticipatory bail was refused by the High Court and the appellant appealed against refusal.",
]
NEW_CASE = (
    "The applicant seeks anticipatory bail under Section 438 of the Code of Criminal Procedure. "
    "Anticipatory bail was refused by the Sessions Court and the applicant appealed against refusal."
)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    return tmp_path


@pytest.fixture
def cases(db_session, add_case):
    def add(n, passages, **kwargs):
        case = add_case(n, passages=passages, **kwargs)
        store_provisions(db_session, case.documents[0], [(i + 1, t) for i, t in enumerate(passages)])
        db_session.flush()

    add(1, BAIL, title="Bail case", year=2022, outcome="Dismissed")
    add(2, ["The accused was convicted under Section 302 IPC after a long trial with many witnesses."], title="Murder", year=2023)
    add(3, BAIL, title="Restricted bail case", year=2023, sensitivity="restricted")
    add(4, BAIL, title="Another bail case", year=2023, outcome="Appeal(s) allowed")


def upload(api, name, content, mime="text/plain"):
    return api.post("/api/uploads", files={"file": (name, content, mime)})


def similar_ids(response) -> list[str]:
    return [r["case"]["display_id"] for r in response.json()["results"]]


def test_text_upload_is_stored_and_described(api, data_dir):
    response = upload(api, "CASE-1042.txt", NEW_CASE.encode())

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "CASE-1042.txt"
    assert body["mime_type"] == "text/plain"
    assert body["passages"] == 1
    assert [p["label"] for p in body["provisions"]] == ["Section 438 CrPC"]
    assert body["warnings"] == []
    assert (data_dir / "uploads" / f"{body['id']}.txt").exists()


def test_pdf_and_word_uploads_are_accepted(api, data_dir):
    pdf = upload(api, "case.pdf", build_pdf([["Anticipatory bail refused."], ["Appeal filed."]]), "application/pdf")
    document = docx.Document()
    document.add_paragraph(NEW_CASE)
    buffer = io.BytesIO()
    document.save(buffer)
    word = upload(api, "case.docx", buffer.getvalue(), "application/octet-stream")

    assert pdf.status_code == word.status_code == 201
    assert pdf.json()["page_count"] == 2
    assert word.json()["page_count"] is None  # Word files have no fixed pages


@pytest.mark.parametrize(
    ("name", "content", "status", "message"),
    [
        ("tool.exe", b"MZ...", 415, "Only PDF"),
        ("fake.pdf", b"<html>not a pdf</html>", 422, "Unsupported file type"),
        ("empty.txt", b"", 422, "empty"),
        ("scan.pdf", build_pdf([None, None]), 422, "No text could be found"),
    ],
)
def test_unacceptable_files_are_rejected_and_not_kept(api, data_dir, name, content, status, message):
    response = upload(api, name, content)

    assert response.status_code == status
    assert message in response.json()["detail"]
    assert not list((data_dir / "uploads").glob("*")) if (data_dir / "uploads").exists() else True


def test_files_over_the_size_limit_are_rejected(api, data_dir, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)

    response = upload(api, "big.txt", b"x" * 10)

    assert response.status_code == 413


def test_the_users_filename_is_never_used_as_a_path(api, data_dir):
    response = upload(api, "..\\..\\evil.txt", NEW_CASE.encode())

    body = response.json()
    assert body["filename"] == "evil.txt"
    assert [p.name for p in data_dir.rglob("*.txt")] == [f"{body['id']}.txt"]
    assert (data_dir / "uploads" / f"{body['id']}.txt").exists()


def test_similar_cases_for_an_upload(api, data_dir, cases):
    upload_id = upload(api, "CASE-1042.txt", NEW_CASE.encode()).json()["id"]

    response = api.post(f"/api/uploads/{upload_id}/similar", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["query"]["kind"] == "upload"
    assert body["query"]["provisions"] == ["Section 438 CrPC"]
    assert set(similar_ids(response)[:2]) == {"TEST-API-1", "TEST-API-4"}
    assert "TEST-API-3" not in similar_ids(response)  # restricted
    top = body["results"][0]
    assert top["match_type"] == "text+provisions"
    assert top["relevance"] == 100
    assert top["shared_provisions"] == ["Section 438 CrPC"]
    assert "Both cite: Section 438 CrPC" in top["reasons"]
    assert top["reasons"][0].startswith("1 of 1 passages of the new case have a close match here")
    pair = top["passage_pairs"][0]
    assert pair["similarity"] >= 0.5
    assert pair["similar_case"]["page_start"] in (1, 2)
    assert any(d.startswith("This case was decided 20") for d in top["differences"])
    assert "Neither is a probability" in body["relevance_note"]
    assert "does not make two cases legally equivalent" in body["relevance_note"]


def test_filters_apply_to_similar_cases(api, data_dir, cases):
    upload_id = upload(api, "CASE-1042.txt", NEW_CASE.encode()).json()["id"]

    response = api.post(f"/api/uploads/{upload_id}/similar", json={"filters": {"year_from": 2023}})

    assert "TEST-API-1" not in similar_ids(response)  # decided 2022
    assert "TEST-API-4" in similar_ids(response)


def test_similar_to_an_existing_case_excludes_itself_and_compares_outcomes(api, cases):
    response = api.get("/api/cases/TEST-API-1/similar")

    assert response.status_code == 200
    ids = similar_ids(response)
    assert "TEST-API-1" not in ids
    assert ids[0] == "TEST-API-4"
    differences = response.json()["results"][0]["differences"]
    assert "Different recorded outcome: Dismissed (this case: Appeal(s) allowed)" in differences
    assert "Decided in different years: 2022 vs 2023" in differences


def test_restricted_case_cannot_be_used_as_the_query(api, cases):
    assert api.get("/api/cases/TEST-API-3/similar").status_code == 404


def test_without_the_model_only_shared_provisions_are_used(api, data_dir, cases):
    app.dependency_overrides[get_embedder] = lambda: None
    created = upload(api, "CASE-1042.txt", NEW_CASE.encode()).json()

    response = api.post(f"/api/uploads/{created['id']}/similar", json={})

    assert "similarity will use shared provisions only" in created["warnings"][0]
    assert "unavailable" in response.json()["notices"][0]
    assert {r["match_type"] for r in response.json()["results"]} == {"provisions"}


def test_long_documents_are_sampled_evenly(api, data_dir, cases):
    long_text = " ".join(f"Sentence number {i} about anticipatory bail and its refusal." for i in range(2200))
    created = upload(api, "long.txt", long_text.encode()).json()

    response = api.post(f"/api/uploads/{created['id']}/similar", json={})

    assert created["passages"] > 60
    assert response.json()["query"]["passages_used"] == 60
    assert "compared using 60 of its" in response.json()["notices"][0]


def test_get_and_delete_an_upload(api, data_dir):
    upload_id = upload(api, "CASE-1042.txt", NEW_CASE.encode()).json()["id"]

    assert api.get(f"/api/uploads/{upload_id}").status_code == 200
    assert api.delete(f"/api/uploads/{upload_id}").status_code == 204
    assert api.get(f"/api/uploads/{upload_id}").status_code == 404
    assert not (data_dir / "uploads" / f"{upload_id}.txt").exists()
