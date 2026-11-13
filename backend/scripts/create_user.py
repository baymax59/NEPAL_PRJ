"""Create a user account, or set a new password for an existing one.

Run from the backend folder:
    uv run python -m scripts.create_user alice --role analyst --clearance restricted --name "Alice Rao"
    uv run python -m scripts.create_user alice --reset-password
    uv run python -m scripts.create_user alice --deactivate --by admin      (someone leaves; history is kept)
    uv run python -m scripts.create_user alice --reactivate --by admin
    uv run python -m scripts.create_user ravi --role analyst --org-role supervisor --clearance restricted --name "Ravi K"
    uv run python -m scripts.create_user ravi --set-org-role investigator --by admin
The password is typed in (not shown); it needs at least 12 characters.

Roles: viewer (search and read), analyst (+ upload new cases), admin (+ read the audit log).
Case Management roles (--org-role; default from --role: admin -> super_admin, analyst -> investigator,
viewer -> viewer): super_admin, administrator, supervisor, investigator, sub_investigator, analyst, viewer.
Everyone but a Super Admin works at a police station: --station CODE (default: the organisation's default station, HQ).
This tool is for the first accounts (the Super Admin); later accounts are made by the people above them, from the screens,
and only for an officer in the register. A role change here counts as a promotion: it adds no power over existing cases.
Clearance: the highest sensitivity the user may see: public, internal, restricted, confidential.
"""

import argparse
import datetime as dt
import getpass
import sys

from sqlalchemy import select

from app.audit.log import AuditLog
from app.auth.passwords import hash_password
from app.auth.users import create_user
from app.casemgmt.enums import AuthorizationChange, OrgRole
from app.casemgmt.models import AuthorizationEvent, PoliceStation
from app.core.enums import AuditOutcome, Role, Sensitivity
from app.db.models import User
from app.db.session import SessionLocal


def ask_password(from_stdin: bool = False) -> str:
    if from_stdin:  # for automation: echo $PASSWORD | ... --password-stdin
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("Password (min 12 characters): ")
    if first != getpass.getpass("Repeat password: "):
        sys.exit("Passwords did not match.")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("--role", choices=[r.value for r in Role], default=Role.VIEWER.value)
    parser.add_argument("--clearance", choices=[s.value for s in Sensitivity], default=Sensitivity.PUBLIC.value)
    parser.add_argument("--name", default="", help="display name")
    parser.add_argument("--reset-password", action="store_true", help="set a new password for an existing user")
    parser.add_argument("--password-stdin", action="store_true", help="read the password from standard input")
    parser.add_argument("--deactivate", action="store_true", help="block the account: no login, old tokens stop working")
    parser.add_argument("--reactivate", action="store_true", help="allow a deactivated account to log in again")
    parser.add_argument("--by", help="the administrator making the change (needed with --deactivate/--reactivate/--set-org-role)")
    parser.add_argument("--org-role", choices=[r.value for r in OrgRole], help="Case Management role of a new user")
    parser.add_argument("--set-org-role", choices=[r.value for r in OrgRole], help="change an existing user's Case Management role")
    parser.add_argument("--station", help="the police station code of a new user (default: HQ)")
    args = parser.parse_args()

    with SessionLocal() as session:
        if args.set_org_role:
            if not args.by:
                sys.exit("--by <administrator> is required, for the audit log.")
            user = session.scalar(select(User).where(User.username == args.username.lower()))
            if user is None:
                sys.exit(f"No user '{args.username}'.")
            actor = session.scalar(select(User).where(User.username == args.by.lower()))
            if actor is None:
                sys.exit(f"No user '{args.by}'.")
            old, user.org_role = user.org_role, args.set_org_role
            user.org_role_since = dt.datetime.now(dt.UTC)  # a promotion adds no power over cases that already exist
            session.add(AuthorizationEvent(organization_id=user.organization_id, user_id=user.id, change=AuthorizationChange.ROLE_CHANGED.value,
                                           old_value=old, new_value=user.org_role, actor_id=actor.id,
                                           reason="Changed with scripts.create_user --set-org-role"))
            session.commit()
            AuditLog(client_ip="cli").record(
                "user.org_role_changed", AuditOutcome.SUCCESS, username=args.by, target_type="user", target_id=user.username,
                details={"old": old, "new": user.org_role},
            )
            print(f"{user.username}: Case Management role {old} -> {user.org_role}.")
            return
        if args.deactivate or args.reactivate:
            if not args.by:
                sys.exit("--by <administrator> is required, for the audit log.")
            user = session.scalar(select(User).where(User.username == args.username.lower()))
            if user is None:
                sys.exit(f"No user '{args.username}'.")
            user.is_active = bool(args.reactivate)
            session.commit()
            action = "user.reactivated" if args.reactivate else "user.deactivated"
            AuditLog(client_ip="cli").record(
                action, AuditOutcome.SUCCESS, username=args.by, target_type="user", target_id=user.username
            )
            print(f"{user.username} is now {'active' if user.is_active else 'deactivated'}.")
            return
        if args.reset_password:
            user = session.scalar(select(User).where(User.username == args.username.lower()))
            if user is None:
                sys.exit(f"No user '{args.username}'.")
            try:
                user.password_hash = hash_password(ask_password(args.password_stdin))
            except ValueError as exc:
                sys.exit(str(exc))
            user.failed_logins, user.locked_until = 0, None
            session.commit()
            print(f"Password updated for {user.username}.")
            return
        station_ids = None
        if args.station:
            station = session.scalar(select(PoliceStation).where(PoliceStation.code == args.station.strip()))
            if station is None:
                sys.exit(f"No police station with the code '{args.station}'.")
            station_ids = [station.id]
        try:
            user = create_user(session, args.username, args.name, ask_password(args.password_stdin), Role(args.role),
                               Sensitivity(args.clearance), OrgRole(args.org_role) if args.org_role else None, station_ids=station_ids)
        except ValueError as exc:
            sys.exit(str(exc))
        session.commit()
        print(f"Created {user.username}: role {user.role}, Case Management role {user.org_role}, clearance {user.clearance}.")


if __name__ == "__main__":
    main()
