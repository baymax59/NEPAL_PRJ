"""Prepare the throwaway database for the browser walk-through of the Knight Hawk screens (Step 15.4).

    uv run python -m scripts.e2e_prepare

It drops and re-creates the database casesdb_e2e, brings it to the latest migration and adds six FICTIONAL
accounts (one per organisation role) that share the test-only password below.

Why a database of its own: Case Management records can't be deleted, by design (database triggers refuse it).
A walk-through creates cases, so it needs a database that can be thrown away as a whole. This script refuses
to touch any database whose name does not contain _e2e (casesdb_e2e by default, or the one in E2E_DB), and never touches the development database (casesdb).
"""

import os
import subprocess  # nosec B404 - runs this project's own migrations (alembic) with fixed arguments
import sys

E2E_DB = os.environ.get("E2E_DB", "casesdb_e2e")  # another throwaway database may run next to the preview, e.g. E2E_DB=casesdb_e2e_full
if not E2E_DB.endswith("_e2e") and "_e2e_" not in E2E_DB:  # never the development database, never one that is not clearly a throwaway
    sys.exit(f"Refusing: {E2E_DB!r} is not a throwaway database name (it must contain _e2e)")
os.environ["POSTGRES_DB"] = E2E_DB  # before the app's settings are read

# Test-only accounts in a throwaway database: not secret, never used anywhere else.
PASSWORD = "Fictional-walkthrough-1"  # nosec B105
USERS = [
    # username, display name, organisation role, Case Intelligence role, clearance
    ("kh.admin", "Asha Rao (fictional)", "super_admin", "admin", "confidential"),
    ("kh.supervisor", "Insp. Devika Menon (fictional)", "supervisor", "analyst", "confidential"),
    ("kh.arun", "SI Arun Kumar (fictional)", "investigator", "analyst", "restricted"),
    ("kh.meena", "SI Meena Iyer (fictional)", "investigator", "analyst", "restricted"),
    ("kh.dev", "Dev Patel (fictional)", "analyst", "analyst", "restricted"),
    ("kh.viewer", "Ravi Shah (fictional)", "viewer", "viewer", "internal"),
]


def main() -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from app.core.config import get_settings

    url = make_url(get_settings().database_url)
    if url.database != E2E_DB:
        sys.exit(f"Refusing: this script only prepares {E2E_DB}, not {url.database}")
    server = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{E2E_DB}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{E2E_DB}"'))
    server.dispose()
    print(f"created an empty {E2E_DB}")

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env={**os.environ, "POSTGRES_DB": E2E_DB})  # nosec B603

    from app.auth.users import create_user
    from app.casemgmt.enums import OrgRole
    from app.core.enums import Role, Sensitivity
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        for username, name, org_role, role, clearance in USERS:
            create_user(session, username, name, PASSWORD, Role(role), Sensitivity(clearance), OrgRole(org_role))
        session.commit()
        print(f"added {len(USERS)} fictional accounts: {', '.join(u[0] for u in USERS)}")
        add_past_cases(session)


# Two FICTIONAL past cases for the knowledge base, so Similar Cases has something to find (CM-5): one like the
# walk-through's case, one unrelated. Invented text; they cite well-known sections only as an example.
PAST_CASES = [
    {"display_id": "FICT-SC-0001", "title": "State v. Unknown caller (FICTIONAL past case): bank officer impersonation and OTP fraud",
     "court": "High Court of Example State (fictional)", "date": "2023-08-14", "outcome": "Conviction upheld (fictional)",
     "passages": ["The accused telephoned the complainant claiming to be a bank officer and asked for the OTP sent to her phone (fictional).",
                  "Within minutes three transfers were made by UPI to a mule account opened with forged KYC documents (fictional).",
                  "The court considered Section 420 IPC and Section 66D of the Information Technology Act, 2000 (fictional judgment)."],
     "provisions": [("ipc|section|420", "Section 420 IPC", "IPC", "420"),
                    ("information technology act|section|66D", "Section 66D of the Information Technology Act", "Information Technology Act", "66D")]},
    {"display_id": "FICT-SC-0002", "title": "Boundary dispute over agricultural land (FICTIONAL past case)",
     "court": "District Court of Example District (fictional)", "date": "2021-02-03", "outcome": "Suit dismissed (fictional)",
     "passages": ["The parties dispute the boundary wall between two survey numbers of agricultural land (fictional).",
                  "The surveyor's report of the revenue department was relied upon (fictional judgment)."],
     "provisions": [("cpc|order_rule|VII-11", "Order VII Rule 11 CPC", "CPC", "VII-11")]},
]


def add_past_cases(session) -> None:
    from app.db.models import DocumentChunk, DocumentProvision
    from app.embeddings.model import load_embedder
    from app.ingestion.store import upsert_case_record
    from app.schemas.case_record import CaseRecord

    try:
        embedder = load_embedder()
    except Exception as exc:  # the model must already be downloaded; similar text is then compared by provisions only
        print(f"embedding model not available ({type(exc).__name__}): past cases are added without meaning vectors")
        embedder = None
    for past in PAST_CASES:
        record = CaseRecord.model_validate({
            "source_system": "fictional_walkthrough", "source_record_id": past["display_id"], "display_id": past["display_id"],
            "sensitivity": "public", "title": past["title"], "court_or_agency": past["court"],
            "outcome": {"text": past["outcome"], "source_field": "fictional"},
            "dates": [{"kind": "decision", "value": past["date"], "source_field": "fictional"}],
            "provenance": {"connector": "e2e_prepare", "connector_version": "1", "retrieved_at": "2026-11-07T00:00:00Z"},
            "documents": [{"doc_type": "judgment", "source_uri": f"fictional://{past['display_id']}"}],
        })
        case, _ = upsert_case_record(session, record)
        document = case.documents[0]
        vectors = embedder.embed_passages(past["passages"]) if embedder else [None] * len(past["passages"])
        for i, (text, vector) in enumerate(zip(past["passages"], vectors, strict=True)):
            session.add(DocumentChunk(document_id=document.id, case_id=case.id, chunk_index=i, page_start=i + 1, page_end=i + 1,
                                      text=text, word_count=len(text.split()), embedding=vector,
                                      embedding_model=embedder.model_name if embedder else None))
        for key, label, act, number in past["provisions"]:
            session.add(DocumentProvision(document_id=document.id, case_id=case.id, provision_key=key, label=label, act=act,
                                          kind=key.split("|")[1], number=number, mention_count=1, pages=[len(past["passages"])]))
    session.commit()
    print(f"added {len(PAST_CASES)} fictional past cases to the knowledge base: {', '.join(p['display_id'] for p in PAST_CASES)}")


if __name__ == "__main__":
    main()
