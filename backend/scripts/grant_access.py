"""Give (or remove) one user need-to-know access to one case above their clearance.

Run from the backend folder:
    uv run python -m scripts.grant_access alice SC-ESCR010000092023 --reason "Assigned to review" --by admin
    uv run python -m scripts.grant_access alice SC-ESCR010000092023 --revoke --by admin
    uv run python -m scripts.grant_access alice SC-ESCR010000092023 --days 30 --reason "..." --by admin
Every grant and revocation is written to the audit log.
"""

import argparse
import datetime as dt
import sys

from sqlalchemy import delete, select

from app.audit.log import AuditLog
from app.core.enums import AuditOutcome
from app.db.models import Case, CaseAccessGrant, User
from app.db.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("display_id")
    parser.add_argument("--by", required=True, help="username of the administrator making the change")
    parser.add_argument("--reason", default="", help="why access is needed (required when granting)")
    parser.add_argument("--days", type=int, help="grant expires after this many days")
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.username == args.username.lower()))
        case = session.scalar(select(Case).where(Case.display_id == args.display_id))
        if user is None or case is None:
            sys.exit("Unknown user or case.")
        details = {"user": user.username, "reason": args.reason, "days": args.days}
        if args.revoke:
            session.execute(delete(CaseAccessGrant).where(CaseAccessGrant.user_id == user.id, CaseAccessGrant.case_id == case.id))
            action = "grant.revoke"
        else:
            if not args.reason.strip():
                sys.exit("--reason is required when granting access.")
            expires = dt.datetime.now(dt.UTC) + dt.timedelta(days=args.days) if args.days else None
            session.execute(delete(CaseAccessGrant).where(CaseAccessGrant.user_id == user.id, CaseAccessGrant.case_id == case.id))
            session.add(CaseAccessGrant(case_id=case.id, user_id=user.id, reason=args.reason, granted_by=args.by, expires_at=expires))
            action = "grant.create"
        session.commit()
    AuditLog(client_ip="cli").record(
        action, AuditOutcome.SUCCESS, username=args.by, target_type="case", target_id=args.display_id, details=details
    )
    print(f"{action}: {args.username} → {args.display_id}")


if __name__ == "__main__":
    main()
