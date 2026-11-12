"""Is the system ready for real police records? The decisions in docs/DECISIONS.md, plus technical checks.

Run from the backend folder (database running):
    uv run python -m scripts.readiness_check
Exit code 0 only when everything is done. Secrets and passwords are compared, never printed.
"""

import datetime as dt
import re
import sys

from sqlalchemy import select

from app.auth.passwords import verify_password
from app.connectors.police_records.fields import CONNECTOR_VERSION
from app.core.config import PROJECT_ROOT, get_settings
from app.db.models import User
from app.db.session import SessionLocal
from app.readiness import decisions, load_labels, read_env, technical_checks


def dev_accounts_in_use() -> list[str]:
    """Active accounts whose password is still the one written in .dev-credentials.txt."""
    file = PROJECT_ROOT / ".dev-credentials.txt"
    if not file.exists():
        return []
    stored = dict(re.findall(r"^(\w+)\s+\(.*password: (\S+)$", file.read_text(encoding="utf-8"), re.M))
    in_use = []
    with SessionLocal() as session:
        for user in session.scalars(select(User).where(User.username.in_(stored), User.is_active.is_(True))):
            if verify_password(stored[user.username], user.password_hash):
                in_use.append(user.username)
    return sorted(in_use)


def show(title: str, checks) -> int:
    done = sum(c.done for c in checks)
    print(f"\n{title}: {done} of {len(checks)} done")
    for check in checks:
        print(f"  [{'done' if check.done else 'OPEN'}] {check.name}: {check.detail}")
    return done


def main() -> None:
    settings = get_settings()
    form = decisions(PROJECT_ROOT / "docs" / "DECISIONS.md")
    technical = technical_checks(
        PROJECT_ROOT,
        read_env(PROJECT_ROOT / ".env"),
        labels=load_labels(PROJECT_ROOT),
        connector_version=CONNECTOR_VERSION,
        audit_retention_days=settings.audit_retention_days,
        dev_accounts_in_use=dev_accounts_in_use(),
        now=dt.datetime.now(dt.UTC),
    )
    print(f"Go-live readiness for real police records ({dt.date.today().isoformat()})")
    done = show("Decisions (docs/DECISIONS.md, signed by your organisation)", form)
    done += show("Technical checks", technical)
    total = len(form) + len(technical)
    print(f"\nOverall: {done} of {total} go-live items done ({100 * done // total}%).")
    print("READY for real police records." if done == total else "NOT ready for real police records yet: see the OPEN items.")
    sys.exit(0 if done == total else 1)


if __name__ == "__main__":
    main()
