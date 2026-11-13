"""Creating users and checking logins."""

import datetime as dt
import re
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, spend_equal_time, verify_password
from app.casemgmt.enums import OrgRole
from app.casemgmt.models import Organization, UserStation
from app.casemgmt.stations import default_station
from app.core.config import get_settings
from app.core.enums import Role, Sensitivity
from app.db.models import User

USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,64}$")


# The Case Management role that matches each Case Intelligence role, unless one is given.
DEFAULT_ORG_ROLE = {Role.ADMIN: OrgRole.SUPER_ADMIN, Role.ANALYST: OrgRole.INVESTIGATOR, Role.VIEWER: OrgRole.VIEWER}


def create_user(
    session: Session,
    username: str,
    display_name: str,
    password: str,
    role: Role,
    clearance: Sensitivity,
    org_role: OrgRole | None = None,
    organization: Organization | None = None,
    *,
    station_ids: Sequence[uuid.UUID] | None = None,
    officer_id: uuid.UUID | None = None,
    assigned_by: uuid.UUID | None = None,
    must_change_password: bool = False,
) -> User:
    """New users join the given organisation, or the first one (the default organisation from migration 0007).
    Everyone but a Super Admin (who sees every station) starts at the given station(s), else at the organisation's default
    station. `officer_id` links the account to its officer in the register (docs/case-management/12 section 4)."""
    username = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Username: 3-64 characters, letters, digits, '.', '_' or '-'")
    if session.scalar(select(User).where(User.username == username)):
        raise ValueError(f"User '{username}' already exists")
    user = User(
        username=username,
        display_name=display_name.strip() or username,
        password_hash=hash_password(password),
        role=Role(role).value,
        clearance=Sensitivity(clearance).value,
        org_role=(org_role or DEFAULT_ORG_ROLE[Role(role)]).value,
        organization_id=(organization or session.scalars(select(Organization).order_by(Organization.created_at)).first()).id,
        officer_id=officer_id,
        must_change_password=must_change_password,
    )
    session.add(user)
    session.flush()
    if station_ids is not None:
        for station_id in dict.fromkeys(station_ids):
            session.add(UserStation(user_id=user.id, station_id=station_id, assigned_by=assigned_by))
        session.flush()
    elif user.org_role != OrgRole.SUPER_ADMIN.value:
        station = default_station(session, user.organization_id)
        if station is not None:
            session.add(UserStation(user_id=user.id, station_id=station.id, assigned_by=assigned_by))
            session.flush()
    return user


def authenticate(session: Session, username: str, password: str) -> tuple[User | None, str]:
    """(user, "ok") on success, else (None, reason). The reason is for the audit log only:
    the person logging in always gets the same message, so it can't reveal which accounts exist."""
    settings = get_settings()
    now = dt.datetime.now(dt.UTC)
    user = session.scalar(select(User).where(User.username == username.strip().lower()))

    if user is None:
        spend_equal_time(password)
        return None, "unknown_user"
    if not user.is_active:
        spend_equal_time(password)
        return None, "inactive"
    if user.locked_until is not None and user.locked_until > now:
        spend_equal_time(password)
        return None, "locked"

    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        reason = "wrong_password"
        if user.failed_logins >= settings.max_failed_logins:
            user.locked_until = now + dt.timedelta(minutes=settings.lockout_minutes)
            user.failed_logins = 0
            reason = "wrong_password_now_locked"
        session.commit()
        return None, reason

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    session.commit()
    return user, "ok"
