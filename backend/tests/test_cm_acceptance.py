"""Case Management: the final acceptance scenario of spec §27, end to end, as one automated test (the plain case design).

The story (scripts/demo/story.py) does the 17 steps through the HTTP API as the people of the spec would, and checks
every answer. This test then checks the outcome again, independently, from the database records and the stored
files: the folders made at registration, the team, the numbered history rebuilt from its rows and its chain checked, the
wrong note kept unchanged as version 1 of two, the refused attempts in the audit log, the audit hash chain, the evidence
files re-hashed, and what the signed report says.

All names, numbers and facts are fictional (scripts/demo/files.py).
"""

import hashlib
import ipaddress
import re
from types import SimpleNamespace

import pytest
from cm_support import create_case
from sqlalchemy import func, select

from app.casemgmt import history
from app.casemgmt.governance import audit_chain
from app.casemgmt.models import (
    Artifact,
    ArtifactVersion,
    CaseEntry,
    CaseFamily,
    CaseFolder,
    CaseMember,
    CustodyEvent,
    EvidenceItem,
    EvidenceObject,
    EvidenceVersion,
)
from app.db.models import AuditEvent, User
from app.documents.extract import extract
from scripts import demo_case
from scripts.demo import files as demo
from scripts.demo import story


def demo_team(cm_client) -> story.Team:
    admin = cm_client("demo.admin", "super_admin", "confidential")
    supervisor = cm_client("demo.supervisor", "supervisor", "confidential")
    arun = cm_client("demo.arun", "investigator", "restricted")
    meena = cm_client("demo.meena", "investigator", "restricted")
    dev = cm_client("demo.dev", "analyst", "restricted")
    clients = {"admin": admin, "supervisor": supervisor, "arun": arun, "meena": meena, "dev": dev}
    return story.Team(admin=admin, supervisor=supervisor, arun=arun, meena=meena, dev=dev,
                      ids={k: str(c.user.id) for k, c in clients.items()})


def test_the_final_acceptance_scenario_works_end_to_end(cm_client, db_session, evidence_store, tmp_path):
    team = demo_team(cm_client)
    told: list[str] = []
    result = story.run(team, log=told.append)

    # The story did all 17 steps, in the spec's order, each with what it showed.
    assert result.done == list(range(1, 18))
    assert [line.split(".")[0].strip().removeprefix("[ok]").strip() for line in told] == [str(n) for n in range(1, 18)]
    assert re.fullmatch(r"[A-Z0-9]+-\d{4}-0001", result.display_id)  # the first case of a fresh database (the demo: KH-2026-0001)
    assert not [line for line in told if re.search(r"commit|branch|clone|merge|repositor", line, re.IGNORECASE)]  # the story speaks plain words

    # The folders made at registration from the case's type, and the one the Investigator added: permanent, flat.
    family = db_session.scalar(select(CaseFamily).where(CaseFamily.display_id == result.display_id))
    folders = db_session.scalars(select(CaseFolder).where(CaseFolder.case_family_id == family.id)).all()
    system = {"imports"} if result.imports else set()  # the folder the system makes the first time a finding is imported
    assert {f.name for f in folders} == set(result.folders) | {story.FOLDER} | system and len(folders) == len(result.folders) + 1 + len(system)
    assert {f.name for f in folders if f.system} == system and result.imports  # the story imported three findings from the test source

    # The team, from its records: the lead, a Sub Investigator and an Analyst, added directly by the Investigator.
    members = {str(m.user_id): m for m in db_session.scalars(select(CaseMember).where(CaseMember.case_family_id == family.id))}
    assert {k: m.role for k, m in members.items()} == {team.ids["arun"]: "lead", team.ids["meena"]: "sub_investigator", team.ids["dev"]: "analyst"}
    assert members[team.ids["meena"]].granted_by == members[team.ids["dev"]].granted_by == team.arun.user.id
    assert all(m.revoked_at is None for m in members.values())

    # The history, rebuilt from its rows: numbered 1, 2, 3 without gaps, each entry tied to the one before, intact.
    entries = db_session.scalars(select(CaseEntry).where(CaseEntry.case_family_id == family.id).order_by(CaseEntry.seq)).all()
    assert [e.seq for e in entries] == list(range(1, len(entries) + 1))
    assert entries[0].kind == "case_registered" and entries[0].prev_hash is None
    assert all(entries[i].prev_hash == entries[i - 1].entry_hash for i in range(1, len(entries)))
    assert history.verify_chain(db_session, family.id) == {"entries": len(entries), "intact": True, "first_problem": None, "problem": None}
    by_kind = {kind: [e for e in entries if e.kind == kind] for kind in {e.kind for e in entries}}
    assert len(by_kind["evidence_added"]) == 6 and len(by_kind["member_added"]) == 2  # SI Meena and the Analyst (the lead joined with the registration)
    assert len(by_kind["note_revised"]) == 1 and by_kind["note_revised"][0].seq == result.entries["correction"]
    approval = entries[result.entries["approval"] - 1]
    assert approval.kind == "status_changed" and str(approval.actor_id) == team.ids["supervisor"]
    assert entries[result.entries["registered"] - 1].kind == "case_registered"
    assert db_session.scalar(select(func.count()).select_from(CaseEntry).where(CaseEntry.case_family_id == family.id)) == len(entries)

    # The wrong note: two versions, version 1 exactly as written (the error kept as its record), version 2 the correction.
    wrong = db_session.get(Artifact, result.notes["wrong"]["id"])
    versions = db_session.scalars(select(ArtifactVersion).where(ArtifactVersion.artifact_id == wrong.id).order_by(ArtifactVersion.version_number)).all()
    assert [v.version_number for v in versions] == [1, 2]
    assert hashlib.sha256(versions[0].content["text"].encode()).hexdigest() == result.wrong_text_sha256 and demo.OTHER_PHONE in versions[0].content["text"]
    assert demo.SUSPECT_PHONE in versions[1].content["text"] and wrong.display_id in versions[1].content["text"]
    # the correction says what it is based on: the version it replaces, then the three exhibits named in the story
    assert versions[1].derived_from[0] == str(versions[0].id) and len(versions[1].derived_from) == 4 and versions[0].derived_from == []
    shown = team.admin.get(f"/api/v1/artifacts/{wrong.id}/versions").json()["versions"]
    assert [v["version_number"] for v in shown] == [1, 2] and shown[1]["derived_from"] == versions[1].derived_from
    assert versions[1].change_note and "UTC" in versions[1].change_note and versions[1].author_id == team.arun.user.id

    # SI Meena's work is credited to her and still shown to her: she is on the team (nothing was ended).
    meena = team.meena.get("/api/v1/contributions/mine").json()
    assert meena["totals"]["evidence"] == 2 and meena["totals"]["notes"] == 1 and meena["no_longer_open"] == {"entries": 0, "notes": 0, "revisions": 0, "evidence": 0}
    assert {e["kind"] for e in meena["entries"]} == {"evidence_added", "note_added"}

    # Every exhibit: its stored file re-hashed equals the recorded SHA-256 and the original file; custody complete.
    items = db_session.scalars(select(EvidenceItem).where(EvidenceItem.case_family_id == family.id)).all()
    assert len(items) == 6
    originals = {hashlib.sha256(f.content).hexdigest() for f in demo.evidence().values()}
    for item in items:
        version = db_session.scalar(select(EvidenceVersion).where(EvidenceVersion.evidence_item_id == item.id))
        stored = db_session.get(EvidenceObject, version.object_sha256)
        assert evidence_store.hash(stored.storage_key) == version.object_sha256  # the stored bytes, re-hashed now
        assert version.object_sha256 in originals
        kinds = [e.event_type for e in db_session.scalars(select(CustodyEvent).where(CustodyEvent.evidence_item_id == item.id)
                                                            .order_by(CustodyEvent.id))]
        assert kinds[0] in ("collected", "ingested") and "verified" in kinds, (item.display_id, kinds)

    # Step 16's attempts are in the audit log, each against its target; and the whole audit chain still verifies.
    refused = db_session.scalars(select(AuditEvent).where(AuditEvent.action == "cm.destructive_operation.rejected")).all()
    assert len(refused) == len(story.REFUSED_ATTEMPTS) and {e.outcome for e in refused} == {"rejected"}
    targets = {e.target_id for e in refused}
    assert family.display_id in targets and any(t.startswith(f"{family.display_id}/EV-") for t in targets)  # the case, and an exhibit of it
    assert all(e.username == "demo.arun" for e in refused)
    chain = audit_chain.verify(db_session)
    assert chain.intact and chain.events > 0
    # The administrator finds the refusals among every read and change of the case: the "refused" view of its trail.
    refused_view = team.admin.get(f"/api/v1/admin/cases/{family.id}/audit", params={"show": "refused", "limit": 200}).json()
    assert {e["outcome"] for e in refused_view["items"]} <= {"denied", "not_found", "rejected", "error"}
    # five of the six attempts name the case or one of its exhibits; the PUT on an old note version names neither and is recorded against the endpoint
    assert sum(e["action"] == "cm.destructive_operation.rejected" for e in refused_view["items"]) == len(story.REFUSED_ATTEMPTS) - 1
    assert any(e.target_type == "endpoint" and e.target_id.startswith("PUT /api/v1/artifacts/") for e in refused)
    assert team.admin.get(f"/api/v1/admin/cases/{family.id}/audit", params={"limit": 1}).json()["total"] > refused_view["total"]
    assert team.admin.get(f"/api/v1/admin/cases/{family.id}/audit", params={"show": "everything"}).status_code == 422

    # The signed report: what it says (provenance and integrity), and that the downloaded copy is the one recorded.
    assert hashlib.sha256(result.report_pdf).hexdigest() == result.report["sha256"]
    (tmp_path / "report.pdf").write_bytes(result.report_pdf)
    text = " ".join(page.text for page in extract(tmp_path / "report.pdf").pages)
    flat = re.sub(r"\s+", "", text)
    assert family.display_id in text and TITLE_WORDS <= set(text.split())
    # provenance: the exact entry of the history described, as "entry N" (the number the screens show), never as a code
    as_of = result.report["as_of_entry"]
    assert as_of == result.entries["report"] - 1 and f"entry{as_of}" in flat.lower()
    assert entries[as_of - 1].entry_hash[:12] not in flat
    for item in items:  # integrity: every exhibit listed with the result of its check, and no fingerprint printed
        version = db_session.scalar(select(EvidenceVersion).where(EvidenceVersion.evidence_item_id == item.id))
        assert item.display_id in text and version.object_sha256[:32] not in flat, item.display_id
    assert "Original" in text and "SHA-256" not in text
    assert not re.search(r"commit|branch|clone|repositor", text, re.IGNORECASE)
    assert "not automatically" in text.lower() or "admissib" in text.lower()  # never presented as court-admissible by itself


TITLE_WORDS = {"Online", "Banking", "Fraud", "Investigation"}


def test_the_demonstration_data_is_fictional_and_stable():
    files = demo.evidence()
    assert set(files) == {"whatsapp", "statement", "url", "access_log", "cdr", "ipdr"}
    assert demo.bank_statement_pdf() == demo.bank_statement_pdf()  # the same bytes every time: a stable SHA-256
    for f in files.values():
        text = f.content.decode("latin-1")
        assert "FICTIONAL" in text, f.name
        for address in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text):
            ip = ipaddress.ip_address(address)
            documentation = any(ip in ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"))
            assert documentation, f"{f.name}: {address} is not a documentation address (RFC 5737)"
        for domain in re.findall(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|in|net|org|io)\b", text):
            raise AssertionError(f"{f.name}: real-looking domain {domain}")  # only .example domains (RFC 2606)
        for phone in re.findall(r"\+91\s?\d{5}\s?\d{5}|\b91\d{10}\b|\+91\d{10}", text):
            digits = re.sub(r"\D", "", phone)[-10:]
            assert digits.startswith("70000000") or digits == "9845012345", f"{f.name}: {phone}"
    # The story's people are fictional accounts made for it, never real ones.
    assert "fictional" in story.DESCRIPTION.lower() and "INR 250000" in story.DESCRIPTION


# ---------------------------------------------------------------- the seed (scripts.demo_case)

DEV = SimpleNamespace(environment="development", cm_mfa_required=False)


def test_the_seed_refuses_where_it_must_and_never_seeds_twice(cm_client, db_session):
    assert demo_case.preflight(db_session, DEV) == (None, [])  # a fresh organisation: the demonstration would be number 0001
    production = demo_case.preflight(db_session, SimpleNamespace(environment="production", cm_mfa_required=False))[1]
    assert len(production) == 1 and "production database" in production[0]
    assert "CM_MFA_REQUIRED" in demo_case.preflight(db_session, SimpleNamespace(environment="development", cm_mfa_required=True))[1][0]

    create_case(cm_client("inv.someone"))  # a real case first: the demonstration would not get number 0001
    problems = demo_case.preflight(db_session, DEV)[1]
    assert len(problems) == 1 and "--any-number" in problems[0] and demo_case.expected_number("KH")[2:] in problems[0]
    assert demo_case.preflight(db_session, DEV, any_number=True) == (None, [])

    result = story.run(demo_team(cm_client), log=lambda _line: None, with_imports=False)
    assert demo_case.preflight(db_session, DEV) == (result.display_id, [])  # once there, never seeded again
    assert demo_case.find_demo(db_session).display_id == result.display_id


def test_the_fictional_accounts_get_passwords_that_are_kept_but_never_shown(db_session, anonymous_api, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("app.audit.log.AuditLog.record", lambda *args, **kwargs: None)  # the CLI's own audit transaction
    credentials = tmp_path / ".dev-credentials.txt"
    credentials.write_text("# Development accounts\nadmin  (admin, clearance confidential)  password: someone-elses-password\n",
                           encoding="utf-8")
    accounts = demo_case.ensure_accounts(db_session, credentials)
    assert set(accounts) == {"admin", "supervisor", "arun", "meena", "dev"}
    text = credentials.read_text(encoding="utf-8")
    assert text.startswith("# Development accounts\nadmin  (admin") and text.count("Demonstration case KH-2026-0001 (CM-8)") == 1
    kept = demo_case.read_passwords(credentials)
    assert kept["admin"] == "someone-elses-password"  # the existing accounts are left alone
    for key, (username, password) in accounts.items():
        assert kept[username] == password and len(password) >= 20
        user = db_session.scalar(select(User).where(User.username == username))
        assert user.org_role == {"admin": "super_admin", "supervisor": "supervisor", "dev": "analyst"}.get(key, "investigator")
        login = anonymous_api.post("/api/auth/token", data={"username": username, "password": password})
        assert login.status_code == 200 and login.json()["access_token"]
    # Run again: the same accounts and passwords, nothing added; nothing was ever printed.
    assert demo_case.ensure_accounts(db_session, credentials) == accounts
    assert credentials.read_text(encoding="utf-8") == text
    printed = capsys.readouterr()
    assert all(password not in printed.out + printed.err for _, password in accounts.values())


def test_an_account_whose_password_is_unknown_is_not_taken_over(cm_user, db_session, tmp_path):
    cm_user("demo.arun")  # exists, but its password isn't in the file: the seed stops instead of guessing or resetting it
    with pytest.raises(SystemExit, match="reset-password"):
        demo_case.ensure_accounts(db_session, tmp_path / "missing.txt")
