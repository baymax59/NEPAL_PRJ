"""Case Management chain of custody, integrity verification, download links and previews (fictional data)."""

import datetime as dt
import hashlib
import os
import uuid
from types import SimpleNamespace

import jwt
from cm_support import PNG, add_member, create_case, upload
from conftest import auth_header, build_pdf
from sqlalchemy import select, text

from app.casemgmt import evidence
from app.casemgmt.models import IntegrityCheck
from app.casemgmt.storage import key_for


def team(cm_client, db_session):
    supervisor = cm_client("sup.kh", "supervisor")
    lead = cm_client("inv.arun")
    colleague = cm_client("inv.colleague")
    created = create_case(supervisor, lead_investigator_id=str(lead.user.id), supervisor_id=str(supervisor.user.id))
    case_id = created["case_id"]
    add_member(lead, case_id, colleague.user)
    exhibit = upload(lead, case_id, PNG, "whatsapp-message.png")["evidence"]
    return SimpleNamespace(supervisor=supervisor, lead=lead, colleague=colleague, created=created, id=case_id, exhibit=exhibit,
                           url=f"/api/v1/evidence/{exhibit['id']}")


def act(client, case, status: int = 200, **body) -> dict:
    response = client.post(f"{case.url}/custody", json={k: str(v) if isinstance(v, uuid.UUID) else v for k, v in body.items()})
    assert response.status_code == status, response.text
    return response.json()


def holder(view: dict) -> str | None:
    custodian = view["current_custodian"]
    return (custodian["user"] or {}).get("username") or custodian["name"]


def test_a_transfer_is_complete_only_when_the_receiver_acknowledges(cm_client, db_session):
    case = team(cm_client, db_session)
    viewer = cm_client("viewer.one", "viewer")
    add_member(case.lead, case.id, viewer.user, "viewer")

    view = act(case.lead, case, action="transfer", to_user_id=case.colleague.user.id, reason="For CDR comparison (fictional)",
               method="sealed envelope, hand delivery", authorization_ref="Order 7/2026 (fictional)")
    pending = view["pending_transfer"]
    assert holder(view) == "inv.arun" and pending["to_custodian"]["user"]["username"] == "inv.colleague"
    assert act(case.lead, case, 409, action="transfer", to_user_id=case.supervisor.user.id, reason="A second transfer")[
        "pending_transfer"] == pending["id"]
    act(viewer, case, 403, action="acknowledge", transfer_event_id=pending["id"])
    act(case.lead, case, 403, action="acknowledge", transfer_event_id=pending["id"])  # the sender can't confirm receipt
    act(case.colleague, case, 422, action="acknowledge", transfer_event_id=pending["id"] + 1000)

    view = act(case.colleague, case, action="acknowledge", transfer_event_id=pending["id"], reason="Received sealed (fictional)")
    acknowledged = view["events"][-1]
    assert holder(view) == "inv.colleague" and view["pending_transfer"] is None
    assert (acknowledged["related_event_id"], acknowledged["verification_sha256"], acknowledged["details"]) == (
        pending["id"], case.exhibit["sha256"], {"integrity": "match"})
    assert [e["event_type"] for e in view["events"]] == ["ingested", "transferred", "acknowledged"]
    act(case.lead, case, 403, action="transfer", to_user_id=case.supervisor.user.id, reason="No longer the custodian")
    assert case.lead.get(case.url).json()["custodian"]["user"]["username"] == "inv.colleague"


def test_declined_transfers_and_outside_bodies(cm_client, db_session):
    case = team(cm_client, db_session)
    pending = act(case.lead, case, action="transfer", to_user_id=case.colleague.user.id, reason="Analysis (fictional)")["pending_transfer"]
    view = act(case.colleague, case, action="decline", transfer_event_id=pending["id"], reason="Not my exhibit (fictional)")
    assert holder(view) == "inv.arun" and view["events"][-1]["details"] == {"declined_by": "receiver"}
    pending = act(case.lead, case, action="transfer", to_user_id=case.colleague.user.id, reason="Analysis (fictional)")["pending_transfer"]
    assert act(case.lead, case, action="decline", transfer_event_id=pending["id"], reason="Sent by mistake")["events"][-1][
        "details"] == {"declined_by": "sender"}

    stranger = cm_client("inv.stranger")  # same organisation, not on the case
    for body in ({"to_user_id": stranger.user.id, "reason": "Someone who can't see it"},
                 {"to_external": "State FSL (fictional)", "reason": "Without a receipt"},
                 {"to_user_id": case.colleague.user.id, "to_external": "State FSL (fictional)", "reason": "Both at once"},
                 {"to_user_id": case.colleague.user.id, "reason": "x"}):
        act(case.lead, case, 422, action="transfer", **body)

    view = act(case.lead, case, action="transfer", to_external="State Forensic Science Laboratory (fictional)",
               receipt_reference="FSL/IN/0042 (fictional)", reason="Device image examination (fictional)")
    assert holder(view) == "State Forensic Science Laboratory (fictional)" and view["pending_transfer"] is None
    assert view["events"][-1]["details"] == {"receipt_reference": "FSL/IN/0042 (fictional)"}
    act(case.lead, case, 403, action="transfer", to_user_id=case.colleague.user.id, reason="The lab has it")
    pending = act(case.supervisor, case, action="transfer", to_user_id=case.lead.user.id, reason="Returned by the lab (fictional)")[
        "pending_transfer"]
    assert pending["from_custodian"] == {"user": None, "name": "State Forensic Science Laboratory (fictional)"}
    assert holder(act(case.lead, case, action="acknowledge", transfer_event_id=pending["id"])) == "inv.arun"


def tamper(evidence_store, sha256: str, content: bytes | None) -> None:
    """What someone with access to the server could do behind the application's back."""
    path = evidence_store.local_path(key_for(sha256))
    os.chmod(path, 0o644)
    if content is None:
        path.unlink()
    else:
        path.write_bytes(content)


def test_verification_detects_a_tampered_file(cm_client, db_session, evidence_store):
    case = team(cm_client, db_session)
    other = upload(case.lead, case.id, b"Complaint text (FICTIONAL)", "complaint.txt", folder="complainant", title="Complaint (fictional)")
    assert case.lead.post(f"{case.url}/verify").json()["result"] == "match"

    tamper(evidence_store, case.exhibit["sha256"], PNG.replace(b"OTP", b"PIN"))  # one word changed
    check = case.lead.post(f"{case.url}/verify").json()
    assert check["result"] == "mismatch" and check["recorded_sha256"] == case.exhibit["sha256"]
    assert check["computed_sha256"] == hashlib.sha256(PNG.replace(b"OTP", b"PIN")).hexdigest()
    custody = case.lead.get(f"{case.url}/custody").json()["events"]
    assert [e["details"].get("result") for e in custody if e["event_type"] == "verified"] == ["match", "mismatch"]

    # A changed file is never sent or shown, and the refusal itself stays on record.
    link = case.lead.post(f"{case.url}/download-token").json()["url"]
    refused = case.lead.get(link)
    assert refused.status_code == 409 and refused.json()["integrity"] == "mismatch"
    assert db_session.scalar(select(IntegrityCheck.result).where(IntegrityCheck.trigger == "download")) == "mismatch"

    admin = cm_client("admin.kh", "super_admin", "restricted")
    report = admin.get("/api/v1/admin/evidence-integrity").json()
    # The complaint's hash was checked when Case Intelligence read its text, right after the upload (CM-5).
    assert report["counts"] == {"match": 1, "mismatch": 1, "missing": 0, "never_checked": 0}
    assert [i["evidence"]["display_id"] for i in report["items"]] == ["EV-0001", "EV-0002"]  # the failure first

    tamper(evidence_store, other["evidence"]["sha256"], None)
    gone = case.lead.post(f"/api/v1/evidence/{other['evidence']['id']}/verify").json()
    assert (gone["result"], gone["computed_sha256"]) == ("missing", None)
    assert case.lead.get(f"/api/v1/evidence/{other['evidence']['id']}/preview").status_code == 409


def test_the_integrity_sweep_checks_every_stored_file(cm_client, db_session, evidence_store):
    case = team(cm_client, db_session)
    upload(case.lead, case.id, b"Complaint text (FICTIONAL)", "complaint.txt", folder="complainant", title="Complaint (fictional)")
    tamper(evidence_store, case.exhibit["sha256"], b"changed")
    checks = evidence.sweep(db_session, evidence_store, case.supervisor.user)
    assert sorted(c.result for c in checks) == ["match", "mismatch"] and {c.trigger for c in checks} == {"scheduled"}


def test_a_download_link_works_once_for_its_user_and_is_a_custody_event(cm_client, db_session, anonymous_api):
    case = team(cm_client, db_session)
    link = case.lead.post(f"{case.url}/download-token").json()
    token = link["url"].rsplit("/", 1)[1]
    assert dt.datetime.fromisoformat(link["expires_at"]) <= dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5, seconds=5)

    response = anonymous_api.get(link["url"])  # no login header needed: the link names its user
    assert response.status_code == 200 and response.content == PNG
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith('attachment; filename="whatsapp-message.png"')
    assert (response.headers["x-content-type-options"], response.headers["cache-control"]) == ("nosniff", "no-store")
    accessed = case.lead.get(f"{case.url}/custody").json()["events"][-1]
    assert (accessed["event_type"], accessed["method"], accessed["actor"]["username"]) == ("accessed", "download", "inv.arun")
    assert accessed["verification_sha256"] == case.exhibit["sha256"]
    assert anonymous_api.get(link["url"]).status_code == 410  # used already

    assert anonymous_api.get(link["url"][:-4] + "abcd").status_code == 404  # forged
    now = dt.datetime.now(dt.UTC)
    expired = jwt.encode({"sub": str(case.lead.user.id), "evi": case.exhibit["id"], "ver": str(uuid.uuid4()), "jti": "x",
                          "purpose": "evidence-download", "iat": now - dt.timedelta(minutes=10), "exp": now - dt.timedelta(minutes=5)},
                         evidence._token_key(), algorithm="HS256")
    assert anonymous_api.get(f"/api/v1/evidence-downloads/{expired}").status_code == 404
    # A download link is not a login, and a login is not a download link.
    assert anonymous_api.get("/api/v1/cases", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    login = auth_header(case.lead.user)["Authorization"].split()[1]
    assert anonymous_api.get(f"/api/v1/evidence-downloads/{login}").status_code == 404

    # Access is checked again when the link is used: revoked or sealed means no download.
    colleague_link = case.colleague.post(f"{case.url}/download-token").json()["url"]
    db_session.execute(text("UPDATE case_members SET revoked_at = now(), revoked_by = :by WHERE user_id = :user"),
                       {"by": case.supervisor.user.id, "user": case.colleague.user.id})
    db_session.commit()
    assert anonymous_api.get(colleague_link).status_code == 404
    lead_link = case.lead.post(f"{case.url}/download-token").json()["url"]
    case.supervisor.post(f"{case.url}/seal", json={"reason": "Sealed by court order (fictional)"})
    assert anonymous_api.get(lead_link).status_code == 404


def test_previews_are_text_only_and_never_open_active_content(cm_client, db_session):
    case = team(cm_client, db_session)
    statement = upload(case.lead, case.id, "Complainant's statement (FICTIONAL): I received a link…".encode(), "statement.txt",
                       folder="complainant", title="Statement (fictional)")["evidence"]
    pdf = upload(case.lead, case.id, build_pdf([["Bank statement (FICTIONAL)"], ["Page two"]]), "bank-statement.pdf",
                 folder="financial-transactions", title="Bank statement (fictional)")["evidence"]
    page = upload(case.lead, case.id, b"<html><script>steal()</script></html>", "phishing.html", folder="osint",
                  title="Phishing page (fictional)")["evidence"]

    text_view = case.lead.get(f"/api/v1/evidence/{statement['id']}/preview").json()
    assert text_view["kind"] == "text" and text_view["pages"][0]["text"].startswith("Complainant's statement (FICTIONAL)")
    pdf_view = case.lead.get(f"/api/v1/evidence/{pdf['id']}/preview").json()
    assert [p["number"] for p in pdf_view["pages"]] == [1, 2] and "Bank statement" in pdf_view["pages"][0]["text"]
    image = case.lead.get(f"{case.url}/preview").json()
    assert image["kind"] == "none" and "download" in image["reason"]
    active = case.lead.get(f"/api/v1/evidence/{page['id']}/preview").json()
    assert active["kind"] == "none" and "never opened" in active["reason"]
    assert case.lead.get(f"/api/v1/evidence/{page['id']}").json()["can"]["preview"] is False

    for exhibit, expected in ((statement, ["accessed"]), (pdf, ["accessed"]), (case.exhibit, []), (page, [])):
        events = case.lead.get(f"/api/v1/evidence/{exhibit['id']}/custody").json()["events"]
        assert [e["event_type"] for e in events if e["event_type"] == "accessed"] == expected
