"""Seed the fictional demonstration case KH-2026-0001 "Online Banking Fraud Investigation" (phase CM-8, spec §23).

Run from the backend folder while the application is running:
    uv run python -m scripts.demo_case                          through the Docker version, https://localhost:8443
    uv run python -m scripts.demo_case --api http://127.0.0.1:8010 --web http://127.0.0.1:5180 --credentials <file>
    uv run python -m scripts.demo_case --show                   is the demonstration there, and which accounts exist?
    uv run python -m scripts.demo_case --write-files <folder>   the six fictional evidence files, to open and read

What it does:
1. Checks that it may: never with ENVIRONMENT=production; not while two-step verification is required (the fictional
   accounts have none); and only when the organisation has no case yet, so the demonstration gets number 0001
   (KH-2026-0001 with the placeholder prefix KH; --any-number allows another number).
2. Creates five FICTIONAL accounts (demo.admin, demo.supervisor, demo.arun, demo.meena, demo.dev) with generated
   passwords, written only to the git-ignored .dev-credentials.txt (never shown on screen).
3. Logs them in through the API and tells the 17-step story of spec §27 (scripts/demo/story.py) through the same
   endpoints as the screens: the evidence goes into the application's own evidence store, every step is written into
   the case's history and audited, the case report is signed and checked. Nothing is written to the case tables directly.
4. Prints where to look.

Case records can't be deleted: the demonstration case stays in that database for good. Never seed a production database.
"""

import argparse
import datetime as dt
import re
import secrets
import sys
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scripts.demo import files as demo
from scripts.demo import story

PROJECT = Path(__file__).resolve().parents[2]
CREDENTIALS = PROJECT / ".dev-credentials.txt"
CADDY_CA = PROJECT / "caddy-root.crt"
DEFAULT_API = "https://localhost:8443"

# key in story.Team, username, display name, organisation role, Case Intelligence role, clearance. All FICTIONAL.
ACCOUNTS = [
    ("admin", "demo.admin", "Asha Rao, administrator (fictional)", "super_admin", "admin", "confidential"),
    ("supervisor", "demo.supervisor", "DSP Devika Menon, supervisor (fictional)", "supervisor", "analyst", "confidential"),
    ("arun", "demo.arun", "Inspector Arun (fictional)", "investigator", "analyst", "restricted"),
    ("meena", "demo.meena", "SI Meena Iyer (fictional)", "investigator", "analyst", "restricted"),
    ("dev", "demo.dev", "Dev Patel, analyst (fictional)", "analyst", "analyst", "restricted"),
]
CREDENTIAL_LINE = re.compile(r"^(?P<user>\S+)\s+\(.*\)\s+password:\s+(?P<password>\S+)\s*$")
HEADER = ("\n# Demonstration case KH-2026-0001 (CM-8): FICTIONAL accounts made by scripts.demo_case on {day}. Local use only;\n"
          "# they exist only to show the demonstration. Deactivate them with: scripts.create_user <username> --deactivate --by <admin>\n")


# ---------------------------------------------------------------- checks


def find_demo(session: Session):
    """The demonstration case, if it was seeded already (its title and its FICTIONAL description)."""
    from app.casemgmt.models import CaseFamily

    return session.scalar(select(CaseFamily).where(CaseFamily.title == story.TITLE,
                                                   CaseFamily.description.startswith("FICTIONAL DEMONSTRATION CASE")))


def preflight(session: Session, settings, *, any_number: bool = False) -> tuple[str | None, list[str]]:
    """(the display ID of the demonstration if it exists already, the reasons not to seed now)."""
    from app.casemgmt import organisations
    from app.casemgmt.models import CaseFamily

    existing = find_demo(session)
    if existing is not None:
        return existing.display_id, []
    problems = []
    if settings.environment == "production":
        problems.append("ENVIRONMENT is production: fictional demonstration data must never go into a production database.")
    if settings.cm_mfa_required:
        problems.append("CM_MFA_REQUIRED is on: the fictional accounts have no two-step verification, so approvals and other privileged "
                        "steps would be refused. Seed before turning it on, or in another environment.")
    organisation = organisations.default_organisation(session)
    if organisation is None:
        problems.append("There is no organisation yet: run the migrations first (alembic upgrade head).")
        return None, problems
    cases = session.scalar(select(func.count()).select_from(CaseFamily).where(CaseFamily.organization_id == organisation.id)) or 0
    if cases and not any_number:
        problems.append(f"The organisation already has {cases} case(s): the demonstration must be its first case to get the number "
                        f"{expected_number(organisation.code)}. Use --any-number to seed it with the next number anyway.")
    return None, problems


def expected_number(code: str) -> str:
    return f"{code}-{dt.datetime.now(dt.UTC).year}-0001"


# ---------------------------------------------------------------- the fictional accounts and their passwords


def read_passwords(path: Path) -> dict[str, str]:
    """Usernames and passwords from the credentials file (the last line for a username wins)."""
    if not path.is_file():
        return {}
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if (match := CREDENTIAL_LINE.match(line.strip())) is not None:
            found[match["user"]] = match["password"]
    return found


def append_passwords(path: Path, rows: list[tuple[str, str, str]]) -> None:
    """Add (username, description, password) lines under a heading; the file is git-ignored and never printed."""
    if not rows:
        return
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if "Demonstration case KH-2026-0001 (CM-8)" not in text:
        text += HEADER.format(day=dt.date.today().isoformat())
    text += "".join(f"{user}  ({description})  password: {password}\n" for user, description, password in rows)
    path.write_text(text, encoding="utf-8")


def ensure_accounts(session: Session, credentials: Path) -> dict[str, tuple[str, str]]:
    """The five fictional accounts: created when missing (with new passwords), else their known passwords."""
    from app.audit.log import AuditLog
    from app.auth.users import create_user
    from app.casemgmt.enums import OrgRole
    from app.core.enums import AuditOutcome, Role, Sensitivity
    from app.db.models import User

    known = read_passwords(credentials)
    accounts, new_rows, created = {}, [], []
    for key, username, name, org_role, role, clearance in ACCOUNTS:
        user = session.scalar(select(User).where(User.username == username))
        if user is not None:
            if username not in known:
                sys.exit(f"The account {username} exists but its password isn't in {credentials.name}. Set a new one with:\n"
                         f"    uv run python -m scripts.create_user {username} --reset-password\n"
                         f"and add a line '{username}  (...)  password: <it>' to {credentials.name}.")
            if not user.is_active:
                sys.exit(f"The account {username} is deactivated; reactivate it first (scripts.create_user --reactivate).")
            accounts[key] = (username, known[username])
            continue
        password = secrets.token_urlsafe(18)
        create_user(session, username, name, password, Role(role), Sensitivity(clearance), OrgRole(org_role))
        accounts[key] = (username, password)
        new_rows.append((username, f'{org_role} "{name}", clearance {clearance}', password))
        created.append(username)
    append_passwords(credentials, new_rows)  # first the file, so a password is never lost
    session.commit()
    for username in created:
        AuditLog(client_ip="cli").record("user.created", AuditOutcome.SUCCESS, username="scripts.demo_case", target_type="user",
                                         target_id=username, details={"fictional": True, "purpose": "demonstration case (CM-8)"})
    return accounts


# ---------------------------------------------------------------- talking to the running application


def _client(api: str, ca: Path | None, headers: dict | None = None) -> httpx.Client:
    verify: bool | str = str(ca) if ca else True
    return httpx.Client(base_url=api, verify=verify, timeout=180, headers=headers or {})


def log_in(api: str, ca: Path | None, accounts: dict[str, tuple[str, str]]) -> story.Team:
    clients, ids = {}, {}
    for key, (username, password) in accounts.items():
        with _client(api, ca) as anonymous:
            answer = anonymous.post("/api/auth/token", data={"username": username, "password": password})
        token = answer.json().get("access_token") if answer.status_code == 200 else None
        if not token:
            sys.exit(f"{username} couldn't log in through {api} (HTTP {answer.status_code}). Is the API using the same database "
                     "as this script (POSTGRES_DB in .env)?")
        clients[key] = _client(api, ca, {"Authorization": f"Bearer {token}"})
        ids[key] = str(clients[key].get("/api/auth/me").json()["id"])
    return story.Team(admin=clients["admin"], supervisor=clients["supervisor"], arun=clients["arun"], meena=clients["meena"],
                      dev=clients["dev"], ids=ids)


def show(session: Session) -> None:
    from app.casemgmt.models import CaseFolder, CaseMember
    from app.db.models import User

    family = find_demo(session)
    if family is None:
        print("The demonstration case is not in this database.")
    else:
        print(f"{family.display_id}  {family.title}  (FICTIONAL demonstration), status {family.workflow_status}")
        folders = session.scalar(select(func.count()).select_from(CaseFolder).where(CaseFolder.case_family_id == family.id))
        print(f"    {folders} folders")
        for member in session.scalars(select(CaseMember).where(CaseMember.case_family_id == family.id, CaseMember.revoked_at.is_(None))
                                      .order_by(CaseMember.granted_at)):
            user = session.get(User, member.user_id)
            print(f"    {user.username:<16} {member.role}")
    for _, username, name, *_ in ACCOUNTS:
        user = session.scalar(select(User).where(User.username == username))
        print(f"    account {username:<16} {'exists' if user else 'not created'}{'' if not user or user.is_active else ' (deactivated)'}  {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default=DEFAULT_API, help=f"the running application (default {DEFAULT_API})")
    parser.add_argument("--web", help="the web address people open (default: the same as --api, as in the Docker version)")
    parser.add_argument("--ca", type=Path, help="the certificate authority of an HTTPS API (default: caddy-root.crt for localhost)")
    parser.add_argument("--credentials", type=Path, default=CREDENTIALS, help="where the fictional accounts' passwords are kept")
    parser.add_argument("--any-number", action="store_true", help="seed even if the organisation already has cases")
    parser.add_argument("--show", action="store_true", help="say whether the demonstration and its accounts exist")
    parser.add_argument("--write-files", type=Path, metavar="FOLDER", help="write the six fictional evidence files there")
    args = parser.parse_args()

    if args.write_files:
        args.write_files.mkdir(parents=True, exist_ok=True)
        for f in demo.evidence().values():
            (args.write_files / f.name).write_bytes(f.content)
            print(f"  {f.name:<34} {len(f.content):>6} bytes  {f.title}")
        return

    from app.core.config import get_settings
    from app.db.session import SessionLocal

    settings = get_settings()
    with SessionLocal() as session:
        if args.show:
            show(session)
            return
        existing, problems = preflight(session, settings, any_number=args.any_number)
        if existing:
            print(f"The demonstration case is already here: {existing}. Nothing to do (case records are permanent).")
            show(session)
            return
        if problems:
            sys.exit("Not seeding:\n- " + "\n- ".join(problems))
        accounts = ensure_accounts(session, args.credentials)

    ca = args.ca or (CADDY_CA if args.api.startswith("https://localhost") and CADDY_CA.is_file() else None)
    print(f"Seeding the FICTIONAL demonstration case through {args.api} (the 17 steps of spec section 27):")
    team = log_in(args.api, ca, accounts)
    try:
        result = story.run(team)
    except story.StoryError as error:
        sys.exit(f"Stopped: {error}")
    finally:
        for client in (team.admin, team.supervisor, team.arun, team.meena, team.dev):
            client.close()
    web = (args.web or args.api).rstrip("/")
    print(f"""
Demonstration case ready: {result.display_id} "{story.TITLE}" (FICTIONAL).
Open {web} and log in as one of these fictional people (their passwords are in {args.credentials.name}):
    demo.arun        Inspector Arun: leads the case ({web}/kh/case/{result.case_id})
    demo.meena       SI Meena Iyer: Sub Investigator, added straight in; wrote the CDR and IPDR findings
    demo.dev         Dev Patel: Analyst, added straight in
    demo.supervisor  DSP Devika Menon: approved the findings (history entry {result.entries['approval']})
    demo.admin       the administrator: the whole case, its history and its audit trail ({web}/kh/admin/cases/{result.case_id})
Your own administrator account sees all of it too. The signed report: {result.report['display_id']} in the case's Reports tab
(it describes the case as of history entry {result.report['as_of_entry']}).""")


if __name__ == "__main__":
    main()
