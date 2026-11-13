"""Case Management: Case Intelligence inside cases. The text index (once per file), search inside a case (withdrawn files
are not part of it), similar cases (knowledge base and other investigations) with links, the assistant citing exhibit,
version and page, the reconstructed timeline, offence-section suggestions, and the rule that sealed or inaccessible
content never reaches results or answers. All names, numbers and facts are fictional."""

import os
from types import SimpleNamespace

import pytest
from cm_support import PNG, add_note, create_case, history, upload, withdraw
from conftest import build_pdf
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.casemgmt.models import IntegrityCheck, ObjectPage, ObjectText
from app.chat.llm import ChatModelUnavailable, get_chat_model
from app.chat.service import NOT_FOUND
from app.db.models import AuditEvent, DocumentProvision

FIR = (b"First Information Report (FICTIONAL TEST DOCUMENT). On 3 March 2025 the complainant received a call from a "
       b"person claiming to be a bank officer, who asked for the OTP sent to her phone 98450 12345. On 4 March 2025 three "
       b"transfers of INR 85000 each were made by UPI to a mule account. Offences under Section 318(4) of the BNS and "
       b"Section 66D of the Information Technology Act, 2000 are reported.")
KB_PASSAGE = ("The complainant received a call from a person claiming to be a bank officer, who asked for the OTP sent to "
              "her phone. Three transfers were then made by UPI to a mule account (fictional past case).")


class FakeChatModel:
    name = "fake-model"

    def __init__(self):
        self.reply: str | Exception = NOT_FOUND
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages):
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture
def model(app_overrides):
    fake = FakeChatModel()
    app_overrides.dependency_overrides[get_chat_model] = lambda: fake
    return fake


def team(cm_client, lead_clearance: str = "restricted"):
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun", clearance=lead_clearance)
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    return SimpleNamespace(supervisor=supervisor, lead=lead, created=created, case_id=created["case_id"])


def ci(case_id: str, what: str = "") -> str:
    return f"/api/v1/cases/{case_id}/intelligence" + (f"/{what}" if what else "")


def search(client, case_id, query: str, **fields) -> dict:
    response = client.post(ci(case_id, "search"), json={"query": query, **fields})
    assert response.status_code == 200, response.text
    return response.json()


def found_ids(result: dict) -> list[str]:
    return [r["source"]["display_id"] for r in result["results"]]


def add_fir(client, case_id, content: bytes = FIR, name: str = "fir-complaint.txt", **fields) -> dict:
    return upload(client, case_id, content, name, folder="complainant", title=fields.pop("title", "FIR (fictional)"), **fields)


# ---------------------------------------------------------------- the text index


def test_an_uploaded_document_is_read_once_and_shared_by_every_case(cm_client, db_session):
    t = team(cm_client)
    added = add_fir(t.lead, t.case_id)
    sha = added["evidence"]["sha256"]

    # Read right after the upload: once, with its hash checked first and its provisions found.
    stored = db_session.get(ObjectText, ("evidence", sha))
    assert stored.status == "indexed" and stored.chunk_count >= 1 and stored.extractor == "plain-text"
    assert {"bns|section|318", "information technology act|section|66D"} <= {p["key"] for p in stored.provisions}
    check = db_session.scalars(select(IntegrityCheck).where(IntegrityCheck.object_sha256 == sha)).one()
    assert (check.trigger, check.result) == ("indexing", "match")

    # The same file in another case is not read again: both share the one index.
    other = create_case(t.lead, title="Second fictional case")
    add_fir(t.lead, other["case_id"])
    assert db_session.scalar(select(func.count()).select_from(ObjectText).where(ObjectText.sha256 == sha)) == 1
    assert db_session.scalar(select(func.count()).select_from(IntegrityCheck).where(IntegrityCheck.object_sha256 == sha)) == 1

    status = t.lead.get(ci(t.case_id)).json()["coverage"]
    assert status["documents"] == 1 and status["indexed"] == 1 and status["notes"] >= 1 and status["passages"] >= 1


def test_the_index_is_permanent_only_meaning_vectors_may_be_added(cm_client, db_session):
    t = team(cm_client)
    sha = add_fir(t.lead, t.case_id)["evidence"]["sha256"]
    for statement in (f"UPDATE object_texts SET status = 'no_text' WHERE sha256 = '{sha}'",
                      f"DELETE FROM object_pages WHERE sha256 = '{sha}'",
                      f"UPDATE object_chunks SET text = 'changed' WHERE sha256 = '{sha}'",
                      f"DELETE FROM object_chunks WHERE sha256 = '{sha}'"):
        with pytest.raises(DBAPIError, match="Case Management"), db_session.begin_nested():
            db_session.execute(text(statement))
    with db_session.begin_nested():  # a newer model may recompute the meaning vectors
        db_session.execute(text(f"UPDATE object_chunks SET embedding = NULL, embedding_model = NULL WHERE sha256 = '{sha}'"))
    assert db_session.scalar(select(func.count()).select_from(ObjectPage).where(ObjectPage.sha256 == sha)) == 1


def test_coverage_says_what_cannot_be_read_and_a_tampered_file_is_never_read(cm_client, db_session, evidence_store, monkeypatch):
    t = team(cm_client)
    upload(t.lead, t.case_id, PNG)  # an image: no text to read
    monkeypatch.setattr("app.casemgmt.intelligence.index.index_in_background", lambda *args, **kwargs: None)
    added = add_fir(t.lead, t.case_id)

    pending = t.lead.get(ci(t.case_id)).json()["coverage"]
    assert pending["documents"] == 2 and pending["readable"] == 1 and pending["pending"] == ["EV-0002"]
    assert pending["not_readable"][0]["display_id"] == "EV-0001" and "image" in pending["not_readable"][0]["reason"]

    # The stored file is changed behind the application's back: it fails its check and its text is not read.
    stored = next(p for p in (evidence_store.root / "objects").rglob("*") if p.is_file() and p.name.startswith(added["evidence"]["sha256"]))
    os.chmod(stored, 0o644)
    stored.write_bytes(FIR.replace(b"85000", b"95000"))
    response = t.lead.post(ci(t.case_id, "prepare"), json={})
    assert response.status_code == 200, response.text
    coverage = response.json()["coverage"]
    assert coverage["indexed"] == 0 and "no longer the file that was added" in coverage["unreadable"][0]["reason"]
    assert db_session.get(ObjectText, ("evidence", added["evidence"]["sha256"])) is None
    assert db_session.scalars(select(IntegrityCheck.result).where(IntegrityCheck.trigger == "indexing")).all() == ["mismatch"]


# ---------------------------------------------------------------- search inside a case


def test_search_inside_a_case_leaves_out_withdrawn_files(cm_client):
    t = team(cm_client)
    add_fir(t.lead, t.case_id)
    phone_note = add_note(t.lead, t.case_id, title="Phone (fictional)", text="Fictional: the phone 98450 12345 was active near the ATM.")

    now = search(t.lead, t.case_id, '"98450 12345"', mode="keyword")
    assert sorted(found_ids(now)) == ["EV-0001", "NOTE-0001"]
    snippet = now["results"][0]["passages"][0]["snippet"]
    assert any(part["match"] for part in snippet) and all("<" not in part["text"] for part in snippet)

    # A withdrawn note stays in the case's history, but it is not part of the case as it now stands.
    withdraw(t.lead, "artifacts", phone_note["file"]["id"], reason="Entered in the wrong case (fictional)")
    assert found_ids(search(t.lead, t.case_id, '"98450 12345"', mode="keyword")) == ["EV-0001"]

    meaning = search(t.lead, t.case_id, "caller pretending to be from the bank asked for the OTP", mode="semantic")
    assert "EV-0001" in found_ids(meaning) and meaning["results"][0]["passages"][0]["matched_by"] == ["semantic"]
    assert search(t.lead, t.case_id, "the of and")["notices"]  # only common words


def test_a_search_is_audited_without_its_words_and_outsiders_get_404(cm_client, db_session):
    t = team(cm_client)
    add_fir(t.lead, t.case_id)
    search(t.lead, t.case_id, "mule account")
    event = db_session.scalars(select(AuditEvent).where(AuditEvent.action == "cm.intelligence.search")).one()
    assert "mule" not in str(event.details) and event.details["query_length"] == len("mule account")

    outsider = cm_client("inv.meena")
    for response in (outsider.post(ci(t.case_id, "search"), json={"query": "mule"}), outsider.get(ci(t.case_id, "similar")),
                     outsider.get(ci(t.case_id)), outsider.get(ci(t.case_id, "timeline"))):
        assert response.status_code == 404
    assert t.lead.delete(ci(t.case_id, "timeline")).status_code == 405


# ---------------------------------------------------------------- the rule: never more than the user may see


def test_sealed_or_inaccessible_content_never_reaches_results_or_answers(cm_client, add_case, model):
    t = team(cm_client)
    add_fir(t.lead, t.case_id)
    secret = b"Informant statement (FICTIONAL): the codeword BLUEHERON was agreed on 7 March 2025 at the safe house."
    sealed = upload(t.lead, t.case_id, secret, "informant.txt", folder="complainant", title="Informant statement (fictional)")
    seal = t.supervisor.post(f"/api/v1/evidence/{sealed['evidence']['id']}/seal", json={"reason": "Protects an informant (fictional)"})
    assert seal.status_code == 200, seal.text
    add_case(7, title="Past case with the same words", year=2021, passages=[secret.decode()])
    add_case(8, title="Confidential past case", year=2022, sensitivity="confidential", passages=[FIR.decode()])
    outsider = cm_client("inv.meena")
    hidden_case = create_case(outsider, title="An investigation the lead can't open (fictional)")
    add_fir(outsider, hidden_case["case_id"])

    # Search: the sealed exhibit isn't there for the lead; the supervisor, who may see it, finds it.
    assert search(t.lead, t.case_id, "BLUEHERON")["results"] == []
    assert t.lead.get(ci(t.case_id)).json()["coverage"]["documents"] == 1
    assert found_ids(search(t.supervisor, t.case_id, "BLUEHERON")) == ["EV-0002"]

    # The assistant is never given it.
    asked = t.lead.post(ci(t.case_id, "ask"), json={"question": "What is the codeword BLUEHERON?"})
    assert asked.status_code == 200, asked.text
    prompt = model.calls[-1][-1]["content"]
    assert "BLUEHERON" not in prompt.split("QUESTION:")[0] and "EV-0002" not in prompt
    assert all(s["display_id"] != "EV-0002" for s in asked.json()["sources"])

    # Similar cases: the sealed text isn't compared; cases the lead may not see are never shown.
    lead_view = t.lead.get(ci(t.case_id, "similar")).json()
    kb = [r["case"]["display_id"] for r in lead_view["knowledge_base"]]
    assert "TEST-API-7" not in kb and "TEST-API-8" not in kb
    assert all(r["case"]["id"] != hidden_case["case_id"] for r in lead_view["investigations"])
    assert "TEST-API-7" in [r["case"]["display_id"] for r in t.supervisor.get(ci(t.case_id, "similar")).json()["knowledge_base"]]

    # The timeline, read by everyone on the case, never uses it: not even when the supervisor, who may see it, builds it.
    built = t.supervisor.post(ci(t.case_id, "timeline"), json={})
    assert built.status_code == 201, built.text
    events = t.lead.get(ci(t.case_id, "timeline")).json()["timeline"]["events"]
    assert events and all("BLUEHERON" not in e["description"] and e["source"]["display_id"] != "EV-0002" for e in events)


# ---------------------------------------------------------------- similar cases and links


def test_similar_cases_finds_past_cases_and_other_investigations_and_links_them(cm_client, add_case, db_session):
    t = team(cm_client)
    add_fir(t.lead, t.case_id)
    past = add_case(1, title="Bank officer impersonation (fictional past case)", year=2023, passages=[KB_PASSAGE])
    db_session.add(DocumentProvision(document_id=past.documents[0].id, case_id=past.id, provision_key="bns|section|318",
                                     label="Section 318 BNS", act="BNS", kind="section", number="318", mention_count=1, pages=[1]))
    add_case(2, title="Unrelated land dispute (fictional)", year=2020, passages=["Boundary wall and survey numbers of agricultural land."])
    db_session.commit()
    second = create_case(t.lead, title="Another OTP fraud (fictional)")
    add_fir(t.lead, second["case_id"])  # the same file: the strongest signal between investigations

    found = t.lead.get(ci(t.case_id, "similar"))
    assert found.status_code == 200, found.text
    result = found.json()
    kb = result["knowledge_base"][0]
    assert kb["case"]["display_id"] == "TEST-API-1" and kb["linked"] is False
    assert kb["passage_pairs"][0]["new_case"]["source"].startswith("EV-0001 v1")
    assert "Section 318 BNS" in result["query"]["provisions"] and any("Both cite" in r for r in kb["reasons"])
    assert "TEST-API-2" not in [r["case"]["display_id"] for r in result["knowledge_base"]]
    other = result["investigations"][0]
    assert other["case"]["id"] == second["case_id"] and "same_file" in other["match_type"]
    assert other["shared_files"][0]["here"] == ["EV-0001"] and any("same file" in r for r in other["reasons"])

    # Link both: each is an entry of the history with a reason; the past case by its ID.
    linked = t.lead.post(f"/api/v1/cases/{t.case_id}/links", json={
        "knowledge_case": "TEST-API-1", "link_type": "same_method",
        "reason": "Fictional: the same bank-officer script and mule account pattern."})
    assert linked.status_code == 201, linked.text
    made = history(t.lead, t.case_id)[-1]
    assert made["kind"] == "link_added" and made["seq"] == linked.json()["entry"]
    assert t.lead.post(f"/api/v1/cases/{t.case_id}/links", json={
        "target_case_id": second["case_id"], "link_type": "shared_evidence",
        "reason": "Fictional: the same FIR copy is evidence in both."}).status_code == 201

    again = t.lead.get(ci(t.case_id, "similar")).json()
    assert again["knowledge_base"][0]["linked"] is True and again["investigations"][0]["linked"] is True
    links = t.lead.get(f"/api/v1/cases/{t.case_id}/links").json()["outgoing"]
    past_link = next(link for link in links if link["knowledge_case"])
    assert past_link["knowledge_case"]["display_id"] == "TEST-API-1" and past_link["knowledge_visible"] is True


def test_a_link_needs_one_visible_target(cm_client, add_case):
    t = team(cm_client)
    add_case(9, title="Confidential past case (fictional)", year=2022, sensitivity="confidential", passages=["Text."])
    body = {"link_type": "related", "reason": "Fictional reason for a link."}
    url = f"/api/v1/cases/{t.case_id}/links"
    assert t.lead.post(url, json={**body, "knowledge_case": "TEST-API-9"}).status_code == 404
    assert t.lead.post(url, json={**body, "knowledge_case": "NO-SUCH-CASE"}).status_code == 404
    both = {**body, "knowledge_case": "TEST-API-9", "target_case_id": t.created["case_id"]}
    assert t.lead.post(url, json=both).status_code == 422
    assert t.lead.post(url, json=body).status_code == 422


# ---------------------------------------------------------------- the assistant


def test_the_assistant_cites_exhibit_version_and_page(cm_client, model):
    t = team(cm_client)
    statement = build_pdf([["Bank statement (FICTIONAL). On 4 March 2025 INR 85000 was sent by UPI",
                            "to account 000111222333, an account opened by a mule (fictional)."],
                           ["Two more transfers of INR 85000 followed on the same day (fictional)."]])
    exhibit = upload(t.lead, t.case_id, statement, "bank-statement.pdf", folder="financial-transactions",
                     title="Bank statement (fictional)")["evidence"]
    model.reply = "INR 85000 was sent by UPI on 4 March 2025 [S2]. The account was opened in 2024 [S9]."

    response = t.lead.post(ci(t.case_id, "ask"), json={"question": "What happened on 4 March 2025 with the UPI transfer?"})
    assert response.status_code == 200, response.text
    answer = response.json()
    assert "[S2]" in answer["answer"] and "[S9]" not in answer["answer"] and answer["answered"] is True
    assert "References to sources that don't exist were removed from the answer." in answer["notices"]
    cited = answer["sources"][1]
    assert (cited["kind"], cited["display_id"], cited["version_number"], cited["page_start"], cited["cited"]) == (
        "evidence", "EV-0001", 1, 1, True)
    assert answer["sources"][0]["kind"] == "case_record"
    prompt = model.calls[-1][-1]["content"]
    assert 'id_in_case="EV-0001"' in prompt and 'version="1"' in prompt and 'pages="1-' in prompt
    assert model.calls[-1][0]["content"].startswith("You help an authorised police investigator")

    # Once the statement is withdrawn it is no longer a source (only the case record and its summary are).
    withdraw(t.lead, "evidence", exhibit["id"], reason="Uploaded to the wrong case (fictional)")
    later = t.lead.post(ci(t.case_id, "ask"), json={"question": "What happened on 4 March 2025?"}).json()
    assert later["sources"][0]["kind"] == "case_record" and all(s["kind"] != "evidence" for s in later["sources"])


def test_when_the_model_is_down_the_error_is_clear_and_audited(cm_client, model, db_session):
    t = team(cm_client)
    model.reply = ChatModelUnavailable("The chat model is not running. Start Ollama and try again.")
    response = t.lead.post(ci(t.case_id, "ask"), json={"question": "Who is the complainant?"})
    assert response.status_code == 503 and "not running" in response.json()["detail"]
    event = db_session.scalars(select(AuditEvent).where(AuditEvent.action == "cm.intelligence.ask")).one()
    assert event.outcome == "error" and "complainant" not in str(event.details)


# ---------------------------------------------------------------- the timeline


def test_the_timeline_is_rebuilt_as_new_versions_of_one_note(cm_client, db_session):
    t = team(cm_client, lead_clearance="confidential")
    add_fir(t.lead, t.case_id, collected_at="2025-03-06T10:00:00+05:30", collected_by="SI Example (fictional)")
    upload(t.lead, t.case_id, b"Confidential note (FICTIONAL): a meeting took place on 9 March 2025.", "high.txt",
           folder="investigation-notes", title="Above the case (fictional)", classification="confidential")
    first = t.lead.post(ci(t.case_id, "timeline"), json={})
    assert first.status_code == 201, first.text
    built = first.json()
    assert built["version_number"] == 1 and built["display_id"] == "TML-0001"
    made = history(t.lead, t.case_id)[-1]
    assert (made["seq"], made["kind"]) == (built["entry"], "timeline_generated")

    view = t.lead.get(ci(t.case_id, "timeline")).json()["timeline"]
    dates = [e["date"] for e in view["events"]]
    assert dates == sorted(dates) and {"2025-03-03", "2025-03-04", "2025-03-06"} <= set(dates)
    assert "2025-03-09" not in dates  # classified above the case: not everyone on it may read it
    collected = next(e for e in view["events"] if e["kind"] == "evidence_collected")
    assert collected["method"] == "record" and collected["source"]["display_id"] == "EV-0001"
    mention = next(e for e in view["events"] if e["date"] == "2025-03-03")
    assert mention["source"]["display_id"] == "EV-0001" and "bank officer" in mention["description"]

    # A new date in a note, and a rebuild: version 2; version 1 stays in the note's versions.
    add_note(t.lead, t.case_id, title="Bank (fictional)", text="Fictional: the bank froze the mule account on 10 March 2025.")
    second = t.lead.post(ci(t.case_id, "timeline"), json={}).json()
    assert second["version_number"] == 2 and second["display_id"] == "TML-0001"
    assert "2025-03-10" in [e["date"] for e in t.lead.get(ci(t.case_id, "timeline")).json()["timeline"]["events"]]
    versions = t.lead.get(f"/api/v1/artifacts/{built['artifact_id']}/versions").json()["versions"]
    by_number = {v["version_number"]: [e["date"] for e in v["content"]["events"]] for v in versions}
    assert "2025-03-10" in by_number[2] and "2025-03-10" not in by_number[1]


def test_only_people_who_may_add_rebuild_the_timeline_and_it_needs_dates(cm_client):
    t = team(cm_client)
    nothing = t.lead.post(ci(t.case_id, "timeline"), json={})
    assert nothing.status_code == 422 and "No dates" in nothing.json()["detail"]
    add_fir(t.lead, t.case_id)
    viewer = cm_client("viewer.kh", "viewer")
    from cm_support import add_member

    add_member(t.lead, t.case_id, viewer.user, "viewer")
    assert viewer.post(ci(t.case_id, "timeline"), json={}).status_code == 403
    assert viewer.get(ci(t.case_id, "timeline")).json()["timeline"] is None


# ---------------------------------------------------------------- offence sections


def test_offence_sections_come_from_the_case_and_from_similar_past_cases(cm_client, add_case, db_session):
    t = team(cm_client)
    add_fir(t.lead, t.case_id)
    past = add_case(3, title="Impersonation fraud (fictional past case)", year=2022, passages=[KB_PASSAGE])
    db_session.add(DocumentProvision(document_id=past.documents[0].id, case_id=past.id, provision_key="ipc|section|420",
                                     label="Section 420 IPC", act="IPC", kind="section", number="420", mention_count=3, pages=[1]))
    db_session.add(DocumentProvision(document_id=past.documents[0].id, case_id=past.id, provision_key="crpc|section|438",
                                     label="Section 438 CrPC", act="CrPC", kind="section", number="438", mention_count=1, pages=[1]))
    db_session.commit()

    response = t.lead.get(ci(t.case_id, "offences"))
    assert response.status_code == 200, response.text
    result = response.json()
    bns = next(p for p in result["cited_here"] if p["key"] == "bns|section|318")
    assert bns["description"] == "Cheating" and bns["category"] == "criminal_law" and bns["cited_in"][0]["display_id"] == "EV-0001"
    it_act = next(p for p in result["cited_here"] if p["key"] == "information technology act|section|66D")
    assert "personation" in it_act["description"]
    suggested = {s["key"]: s for s in result["from_similar_cases"]}
    assert suggested["ipc|section|420"]["count"] == 1 and suggested["ipc|section|420"]["cases"][0]["display_id"] == "TEST-API-3"
    assert "crpc|section|438" not in suggested  # procedure says nothing about the offence
    assert "not a legal assessment" in result["disclaimer"]


def test_a_case_is_compared_with_past_cases_by_its_own_lower_bar_never_stricter_than_the_one_for_whole_documents(
        cm_client, add_case, db_session, fake_embedder, monkeypatch):
    """The bar for the passages of a registered case is a setting of its own: notes are looser than judgments, so with the single bar
    meant for two judgments the Insights tab stayed empty for every real case."""
    from app.core.config import get_settings

    t = team(cm_client)
    add_fir(t.lead, t.case_id)
    loose = ("A person claiming to be a bank officer asked about the OTP. Later the village market was crowded with travellers buying "
             "vegetables, fruit, cloth, spices, brass pots, bamboo baskets and clay lamps near the river bank on a warm morning.")
    add_case(1, title="Loosely related (fictional past case)", year=2023, passages=[loose])
    db_session.commit()
    a, b = fake_embedder.embed_passages([FIR.decode(), loose])
    similarity = sum(x * y for x, y in zip(a, b, strict=True))
    assert 0.2 < similarity < fake_embedder.min_passage_similarity, similarity  # close enough for the lower bar, not for the whole-document bar

    def found() -> list[str]:
        result = t.lead.get(ci(t.case_id, "similar"), params={"scope": "knowledge_base"}).json()
        return [r["case"]["display_id"] for r in result["knowledge_base"]]

    assert found() == []  # the case-side bar is capped at the whole-document bar (0.5 for the test embedder)
    monkeypatch.setattr(get_settings(), "case_similar_passage_min_similarity", 0.2)
    assert found() == ["TEST-API-1"]
    monkeypatch.setattr(get_settings(), "case_similar_passage_min_similarity", 0.95)  # a higher setting never makes it stricter than 0.5
    assert found() == []
