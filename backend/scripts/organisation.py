"""Show or set up the organisation: its name and the prefix of its case numbers (decision D13).

Run from the backend folder:
    uv run python -m scripts.organisation --show
    uv run python -m scripts.organisation --set-up TSP --name "Example State Police" --by admin
    uv run python -m scripts.organisation --rename TSP --name "Example State Police, Cyber Wing" --by admin

The prefix starts every case number (TSP-2026-0001). It can be changed only until the first case is created:
case numbers are permanent. Every change is recorded in the audit log.
"""

import argparse
import sys

from app.audit.log import AuditLog
from app.casemgmt import organisations
from app.core.enums import AuditOutcome
from app.db.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--show", action="store_true", help="list organisations with their numbers of cases and users")
    parser.add_argument("--set-up", metavar="PREFIX", help="set the default organisation's prefix (before the first case)")
    parser.add_argument("--rename", metavar="PREFIX", help="change the name of the organisation with this prefix")
    parser.add_argument("--name", help="the organisation's name")
    parser.add_argument("--by", help="the administrator making the change (for the audit log)")
    args = parser.parse_args()

    with SessionLocal() as session:
        if args.set_up or args.rename:
            if not args.by or not args.name:
                sys.exit("--name and --by <administrator> are required.")
            try:
                if args.set_up:
                    old, new = organisations.set_up(session, code=args.set_up, name=args.name)
                    action, details = "organisation.set_up", {"old_prefix": old, "new_prefix": new, "name": args.name}
                else:
                    organisations.rename(session, code=args.rename, name=args.name)
                    action, details = "organisation.renamed", {"prefix": args.rename.upper(), "name": args.name}
            except ValueError as exc:
                sys.exit(str(exc))
            session.commit()
            AuditLog(client_ip="cli").record(action, AuditOutcome.SUCCESS, username=args.by, target_type="organisation",
                                             target_id=details.get("new_prefix") or details["prefix"], details=details)
        for row in organisations.overview(session):
            print(f"{row['code']:<8} {row['name']}  ({row['cases']} case(s), {row['users']} user(s))")


if __name__ == "__main__":
    main()
