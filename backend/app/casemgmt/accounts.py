"""Who may create whom, the officer-ID rule, role changes and station assignment
(docs/case-management/12-roles-and-stations.md, sections 2, 4 and 5).

    Super Admin   -> creates Administrators and gives them their stations
    Administrator -> creates Supervisors (at one of the Administrator's stations)
    Supervisor    -> creates Investigators, Sub Investigators, Analysts and Viewers at their station
    Investigator  -> creates Investigators, Sub Investigators and Analysts at their station

Nobody creates a role above their own. An account is made only for an officer in the register (`officer_registry`):
the ID must exist, belong to nobody else, and the role may not be above the highest role the register allows for that
officer. The officer's station comes from the register, never from what is typed.

Every account, role change and station change is a permanent record in the access history (`authorization_events`).
The functions raise Forbidden / Invalid / Conflict; the API turns them into answers and the audit log records the refusals.
"""

import datetime as dt
import re
import secrets
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.access import sensitivities_up_to
from app.auth.users import create_user
from app.casemgmt.access import station_ids
from app.casemgmt.enums import AuthorizationChange, OrgRole, StationStatus
from app.casemgmt.errors import Conflict, Forbidden, Invalid
from app.casemgmt.models import AuthorizationEvent, OfficerRegistry, Organization, PoliceStation, UserStation
from app.casemgmt.notifications import notify
from app.core.enums import Role, Sensitivity
from app.db.models import User

# Higher can do more. The register's "highest role" limits an officer's account to this rank or below.
RANK = {
    OrgRole.VIEWER: 0,
    OrgRole.ANALYST: 1,
    OrgRole.SUB_INVESTIGATOR: 2,
    OrgRole.INVESTIGATOR: 3,
    OrgRole.SUPERVISOR: 4,
    OrgRole.ADMINISTRATOR: 5,
    OrgRole.SUPER_ADMIN: 6,
}
CREATABLE: dict[OrgRole, set[OrgRole]] = {
    OrgRole.SUPER_ADMIN: {OrgRole.ADMINISTRATOR},
    OrgRole.ADMINISTRATOR: {OrgRole.SUPERVISOR},
    OrgRole.SUPERVISOR: {OrgRole.INVESTIGATOR, OrgRole.SUB_INVESTIGATOR, OrgRole.ANALYST, OrgRole.VIEWER},
    OrgRole.INVESTIGATOR: {OrgRole.INVESTIGATOR, OrgRole.SUB_INVESTIGATOR, OrgRole.ANALYST},
}
SEVERAL_STATIONS = {OrgRole.ADMINISTRATOR}  # everybody else works at exactly one station (a Super Admin at all)
OFFICER_NUMBER = re.compile(r"^[A-Z0-9][A-Z0-9._/-]{1,31}$")
# The Case Intelligence role (what a user may do in the similar-case search) that goes with each role.
INTELLIGENCE_ROLE = {OrgRole.SUPER_ADMIN: Role.ADMIN, OrgRole.VIEWER: Role.VIEWER}


@dataclass
class CreatedAccount:
    user: User
    temporary_password: str | None  # shown once to the creator, who hands it over; the owner must replace it at first login


_PASSWORD_LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"  # no 0/O, 1/l/I: it is read out and typed


def new_temporary_password() -> str:
    """Like Kx7m-Rt4p-Hq9w-Zn3c: 16 random characters in four groups (about 93 bits)."""
    return "-".join("".join(secrets.choice(_PASSWORD_LETTERS) for _ in range(4)) for _ in range(4))


def _label(role: OrgRole) -> str:
    return role.value.replace("_", " ")


def _require_role(actor: User, allowed: set[OrgRole], what: str) -> OrgRole:
    if actor.organization_id is None or not actor.is_active:
        raise Forbidden("Your account isn't part of an organisation")
    role = OrgRole(actor.org_role)
    if role not in allowed:
        raise Forbidden(f"Your role ({_label(role)}) can't {what}")
    return role


def _within_reach(session: Session, actor: User, station_id: uuid.UUID) -> bool:
    """The actor may act on people of this station: a Super Admin anywhere, others only at their own station(s)."""
    return actor.org_role == OrgRole.SUPER_ADMIN or station_id in station_ids(actor)


def _event(session: Session, actor: User, user: User, change: AuthorizationChange, old: str | None, new: str | None, reason: str) -> None:
    session.add(AuthorizationEvent(organization_id=user.organization_id, user_id=user.id, change=change.value, old_value=old,
                                   new_value=new, actor_id=actor.id, reason=reason))


def _reason(reason: str | None) -> str:
    reason = (reason or "").strip()
    if not 5 <= len(reason) <= 500:
        raise Invalid("Give a reason (5 to 500 characters)")
    return reason


def _stations(session: Session, actor: User, ids: Iterable[uuid.UUID]) -> list[PoliceStation]:
    found = []
    for station_id in dict.fromkeys(ids):
        station = session.get(PoliceStation, station_id)
        if station is None or station.organization_id != actor.organization_id:
            raise Invalid("Unknown police station")
        if station.status != StationStatus.ACTIVE.value:
            raise Invalid(f"Station {station.code} is inactive")
        found.append(station)
    return found


# ---------------------------------------------------------------- the register of officers


def add_officer(session: Session, actor: User, *, officer_number: str, full_name: str, rank: str, station_id: uuid.UUID,
                highest_role: str) -> OfficerRegistry:
    """Enter a real officer in the register. Only the Super Admin does this."""
    _require_role(actor, {OrgRole.SUPER_ADMIN}, "enter officers in the register")
    number = (officer_number or "").strip().upper()
    if not OFFICER_NUMBER.fullmatch(number):
        raise Invalid("The officer ID is 2 to 32 letters, digits, '.', '_', '/' or '-'")
    if not 3 <= len((full_name or "").strip()) <= 200 or not 2 <= len((rank or "").strip()) <= 64:
        raise Invalid("Give the officer's full name and rank")
    try:
        role = OrgRole(highest_role)
    except ValueError:
        raise Invalid("Unknown role") from None
    if role == OrgRole.SUPER_ADMIN:
        raise Invalid("The register can't allow the Super Admin role: that account is made at installation")
    (station,) = _stations(session, actor, [station_id])
    if session.scalar(select(OfficerRegistry.id).where(OfficerRegistry.organization_id == actor.organization_id,
                                                        OfficerRegistry.officer_number == number)):
        raise Conflict(f"Officer {number} is already in the register")
    officer = OfficerRegistry(organization_id=actor.organization_id, officer_number=number, full_name=full_name.strip(),
                              rank=rank.strip(), station_id=station.id, highest_role=role.value, created_by=actor.id)
    session.add(officer)
    session.flush()
    return officer


def find_officer(session: Session, actor: User, officer_number: str) -> OfficerRegistry:
    officer = session.scalar(select(OfficerRegistry).where(OfficerRegistry.organization_id == actor.organization_id,
                                                           OfficerRegistry.officer_number == (officer_number or "").strip().upper()))
    if officer is None:
        raise Invalid("This officer ID is not in the register: no account can be made for it")
    return officer


# ---------------------------------------------------------------- accounts


def create_account(session: Session, actor: User, *, officer_number: str, username: str, display_name: str, role: str,
                   clearance: str, password: str | None = None, extra_station_ids: Iterable[uuid.UUID] = ()) -> CreatedAccount:
    """Make the account of a registered officer. `extra_station_ids` is for an Administrator, who may have several stations.
    Without a `password` a temporary one is made and returned once; the owner must replace it at their first login."""
    actor_role = _require_role(actor, set(CREATABLE), "create accounts")
    try:
        new_role = OrgRole(role)
    except ValueError:
        raise Invalid("Unknown role") from None
    if new_role not in CREATABLE[actor_role]:
        allowed = ", ".join(_label(r) for r in sorted(CREATABLE[actor_role], key=RANK.get))
        raise Forbidden(f"A {_label(actor_role)} can create only: {allowed}")

    officer = find_officer(session, actor, officer_number)
    if session.scalar(select(User.id).where(User.officer_id == officer.id)):
        raise Conflict(f"Officer {officer.officer_number} already has an account")
    if RANK[new_role] > RANK[OrgRole(officer.highest_role)]:
        raise Forbidden(f"The register allows officer {officer.officer_number} at most the role {_label(OrgRole(officer.highest_role))}")

    station = session.get(PoliceStation, officer.station_id)
    if station.status != StationStatus.ACTIVE.value:
        raise Invalid(f"The officer's station ({station.code}) is inactive")
    if not _within_reach(session, actor, station.id):
        raise Forbidden(f"Officer {officer.officer_number} belongs to station {station.code}, which isn't one of yours")
    stations = [station]
    extra = list(extra_station_ids)
    if extra:
        if new_role not in SEVERAL_STATIONS:
            raise Invalid("Only an Administrator can have more than one station")
        stations += [s for s in _stations(session, actor, extra) if s.id != station.id]
    if any(not _within_reach(session, actor, s.id) for s in stations):
        raise Forbidden("A station isn't one of yours")

    try:
        level = Sensitivity(clearance)
    except ValueError:
        raise Invalid("Unknown clearance") from None
    if level.value not in sensitivities_up_to(actor.clearance):
        raise Forbidden("You can't give an account a clearance above your own")

    temporary = password is None
    password = password or new_temporary_password()
    user = create_user(session, username, display_name, password, INTELLIGENCE_ROLE.get(new_role, Role.ANALYST), level, new_role,
                       station_ids=[s.id for s in stations], officer_id=officer.id, assigned_by=actor.id, must_change_password=temporary)
    _event(session, actor, user, AuthorizationChange.ACCOUNT_CREATED, None, new_role.value,
           f"Account for officer {officer.officer_number} ({officer.full_name})")
    for s in stations:
        _event(session, actor, user, AuthorizationChange.STATION_GRANTED, None, s.code, "Station of the new account")
    session.flush()
    return CreatedAccount(user, password if temporary else None)


SELF_REGISTRATION_REFUSED = (
    "These details don't match the officer register, or this officer already has an account. "
    "Check the officer ID and your full name as written in the register, or ask your Supervisor."
)


def _plain_name(value: str) -> str:
    """A name for comparing: no case, no dots or commas, one space between words."""
    return " ".join(re.sub(r"[.,]", " ", value or "").casefold().split())


def register_yourself(session: Session, *, officer_number: str, full_name: str, username: str, password: str, email: str | None = None,
                      phone: str | None = None) -> tuple[User, str]:
    """An officer creates their own login. It works only for an officer who is in the register (the ID and the full name must match),
    who has no account yet. The account starts with the least access there is: Viewer, public clearance, at the officer's own station
    (from the register, never from what was typed). A Supervisor or Administrator raises it later, within what the register allows.
    One answer for every refusal, so the form can't be used to find out who is in the register."""
    organization = session.scalars(select(Organization).order_by(Organization.created_at)).first()
    number = (officer_number or "").strip().upper()
    officer = None
    if organization is not None:
        officer = session.scalar(select(OfficerRegistry).where(OfficerRegistry.organization_id == organization.id,
                                                               OfficerRegistry.officer_number == number))
    if officer is None or _plain_name(full_name) != _plain_name(officer.full_name) or session.scalar(select(User.id).where(User.officer_id == officer.id)):
        raise Invalid(SELF_REGISTRATION_REFUSED)
    station = session.get(PoliceStation, officer.station_id)
    if station is None or station.status != StationStatus.ACTIVE.value:
        raise Invalid(SELF_REGISTRATION_REFUSED)
    try:
        user = create_user(session, username, officer.full_name, password, Role.VIEWER, Sensitivity.PUBLIC, OrgRole.VIEWER, organization,
                           station_ids=[station.id], officer_id=officer.id, assigned_by=None, must_change_password=False)
    except ValueError as exc:  # a username or password that doesn't fit the rules
        raise Invalid(str(exc)) from None
    if email or phone:  # the profile can be filled in right away
        user.email, user.phone, user.profile_updated_at = (email or None), (phone or None), dt.datetime.now(dt.UTC)
    _event(session, user, user, AuthorizationChange.ACCOUNT_CREATED, None, OrgRole.VIEWER.value,
           f"Created by officer {officer.officer_number} ({officer.full_name}) themselves: view-only until a Supervisor or Administrator raises it")
    _event(session, user, user, AuthorizationChange.STATION_GRANTED, None, station.code, "Station of the new account (from the register)")
    # Those who can raise the access are told: the Super Admins, and the Administrators and Supervisors of this station.
    here = select(UserStation.user_id).where(UserStation.station_id == station.id, UserStation.revoked_at.is_(None))
    people = session.scalars(select(User.id).where(User.organization_id == organization.id, User.is_active.is_(True), User.id != user.id, (
        (User.org_role == OrgRole.SUPER_ADMIN.value)
        | (User.org_role.in_([OrgRole.ADMINISTRATOR.value, OrgRole.SUPERVISOR.value]) & User.id.in_(here))))).all()
    notify(session, people, "account.self_registered", actor=user, officer=officer.officer_number, name=officer.full_name,
           username=user.username, station=station.code)
    session.flush()
    return user, station.code


def profile_view(session: Session, user: User) -> dict:
    """A person's own profile: the official details from the register (read-only) and what they filled in."""
    officer = session.get(OfficerRegistry, user.officer_id) if user.officer_id else None
    stations = [s.code for s in session.scalars(select(PoliceStation).join(UserStation, UserStation.station_id == PoliceStation.id).where(
        UserStation.user_id == user.id, UserStation.revoked_at.is_(None)).order_by(PoliceStation.code))]
    return {"username": user.username, "display_name": user.display_name, "org_role": user.org_role, "clearance": user.clearance,
            "officer_number": officer.officer_number if officer else None, "rank": officer.rank if officer else None, "stations": stations,
            "email": user.email, "phone": user.phone, "job_title": user.job_title, "profile_updated_at": user.profile_updated_at,
            "id": user.id, "photo_updated_at": user.photo_updated_at}


def update_profile(session: Session, user: User, *, email: str | None, phone: str | None, job_title: str | None) -> list[str]:
    """Save what the person filled in about themselves (blank clears a field). Returns the names of the fields that changed."""
    wanted = {"email": (email or "").strip() or None, "phone": (phone or "").strip() or None, "job_title": (job_title or "").strip() or None}
    changed = [name for name, value in wanted.items() if getattr(user, name) != value]
    for name in changed:
        setattr(user, name, wanted[name])
    user.profile_updated_at = dt.datetime.now(dt.UTC)  # saving is what counts, even when nothing changed: the profile has been looked at
    session.flush()
    return changed


def change_role(session: Session, actor: User, user: User, new_role: str, reason: str) -> User:
    """A promotion or demotion among the roles below the actor's own. It adds no power over cases that already exist: the
    moment it takes effect is kept (`org_role_since`) and powers that come from the role itself reach only cases registered
    after it."""
    actor_role = _require_role(actor, {OrgRole.SUPER_ADMIN, OrgRole.ADMINISTRATOR, OrgRole.SUPERVISOR}, "change roles")
    reason = _reason(reason)
    try:
        target = OrgRole(new_role)
    except ValueError:
        raise Invalid("Unknown role") from None
    if user.organization_id != actor.organization_id:
        raise Invalid("Unknown user")
    if user.id == actor.id:
        raise Forbidden("Nobody can change their own role")
    old = OrgRole(user.org_role)
    if target == OrgRole.SUPER_ADMIN or RANK[old] >= RANK[actor_role] or RANK[target] >= RANK[actor_role]:
        raise Forbidden(f"A {_label(actor_role)} can only move people between roles below {_label(actor_role)}")
    if old == target:
        raise Invalid(f"The user is already {_label(target)}")
    mine = station_ids(user)
    if actor.org_role != OrgRole.SUPER_ADMIN and not (mine & station_ids(actor)):
        raise Forbidden("This person doesn't work at one of your stations")
    if user.officer_id is not None:
        officer = session.get(OfficerRegistry, user.officer_id)
        if RANK[target] > RANK[OrgRole(officer.highest_role)]:
            raise Forbidden(f"The register allows officer {officer.officer_number} at most the role {_label(OrgRole(officer.highest_role))}")
    user.org_role = target.value
    user.org_role_since = dt.datetime.now(dt.UTC)  # the real clock: a database transaction's now() doesn't move
    _event(session, actor, user, AuthorizationChange.ROLE_CHANGED, old.value, target.value, reason)
    session.flush()
    return user


def change_clearance(session: Session, actor: User, user: User, new_level: str, reason: str) -> User:
    """Raise or lower the highest sensitivity a person may see. Same reach as a role change: only people below the actor's own role, at
    the actor's own station (a Super Admin anywhere), never one's own, and never above the actor's own clearance."""
    actor_role = _require_role(actor, {OrgRole.SUPER_ADMIN, OrgRole.ADMINISTRATOR, OrgRole.SUPERVISOR}, "change clearances")
    reason = _reason(reason)
    try:
        level = Sensitivity(new_level)
    except ValueError:
        raise Invalid("Unknown clearance") from None
    if user.organization_id != actor.organization_id:
        raise Invalid("Unknown user")
    if user.id == actor.id:
        raise Forbidden("Nobody can change their own clearance")
    if RANK[OrgRole(user.org_role)] >= RANK[actor_role]:
        raise Forbidden(f"A {_label(actor_role)} can only change the clearance of people below {_label(actor_role)}")
    if level.value not in sensitivities_up_to(actor.clearance):
        raise Forbidden("You can't give a clearance above your own")
    if actor.org_role != OrgRole.SUPER_ADMIN and not (station_ids(user) & station_ids(actor)):
        raise Forbidden("This person doesn't work at one of your stations")
    if user.clearance == level.value:
        raise Invalid(f"The clearance is already {level.value}")
    old = user.clearance
    user.clearance = level.value
    _event(session, actor, user, AuthorizationChange.CLEARANCE_CHANGED, old, level.value, reason)
    session.flush()
    return user


def set_stations(session: Session, actor: User, user: User, station_ids_wanted: Iterable[uuid.UUID], reason: str) -> list[PoliceStation]:
    """Set which stations a person works at (an Administrator: one or more, everybody else: exactly one). The Super Admin
    gives an Administrator their stations; an Administrator places Supervisors and others within their own stations.
    Ended assignments are kept (revoked), never deleted."""
    actor_role = _require_role(actor, {OrgRole.SUPER_ADMIN, OrgRole.ADMINISTRATOR}, "assign stations")
    reason = _reason(reason)
    if user.organization_id != actor.organization_id:
        raise Invalid("Unknown user")
    target_role = OrgRole(user.org_role)
    if target_role == OrgRole.SUPER_ADMIN:
        raise Invalid("A Super Admin works at every station: nothing to assign")
    if actor_role == OrgRole.SUPER_ADMIN:
        if target_role != OrgRole.ADMINISTRATOR:
            raise Forbidden("The Super Admin assigns the stations of Administrators; Administrators place everybody else")
    elif target_role in (OrgRole.ADMINISTRATOR,) or RANK[target_role] >= RANK[actor_role]:
        raise Forbidden("An Administrator assigns stations only to people below them")
    stations = _stations(session, actor, station_ids_wanted)
    if not stations:
        raise Invalid("Choose at least one station")
    if len(stations) > 1 and target_role not in SEVERAL_STATIONS:
        raise Invalid(f"A {_label(target_role)} works at exactly one station")
    if any(not _within_reach(session, actor, s.id) for s in stations):
        raise Forbidden("A station isn't one of yours")
    if actor_role == OrgRole.ADMINISTRATOR and not (station_ids(user) & station_ids(actor)):
        raise Forbidden("This person doesn't work at one of your stations")

    wanted = {s.id: s for s in stations}
    current = {row.station_id: row for row in session.scalars(select(UserStation).where(
        UserStation.user_id == user.id, UserStation.revoked_at.is_(None)))}
    for station_id, row in current.items():
        if station_id not in wanted:
            row.revoked_by, row.revoked_at = actor.id, func.now()
            _event(session, actor, user, AuthorizationChange.STATION_REVOKED, session.get(PoliceStation, station_id).code, None, reason)
    for station_id, station in wanted.items():
        if station_id not in current:
            session.add(UserStation(user_id=user.id, station_id=station_id, assigned_by=actor.id))
            _event(session, actor, user, AuthorizationChange.STATION_GRANTED, None, station.code, reason)
    session.flush()
    return stations


# ---------------------------------------------------------------- people in reach


MANAGERS = {OrgRole.SUPER_ADMIN, OrgRole.ADMINISTRATOR, OrgRole.SUPERVISOR}  # who may change, reset or end other people's accounts


def manages(actor: User, person: User) -> bool:
    """The actor looks after this person: someone below their own rank, at one of their stations (a Super Admin: anywhere)."""
    actor_role = OrgRole(actor.org_role)
    if actor_role not in MANAGERS or person.id == actor.id or person.organization_id != actor.organization_id:
        return False
    if RANK[OrgRole(person.org_role)] >= RANK[actor_role]:
        return False
    return actor_role == OrgRole.SUPER_ADMIN or bool(station_ids(person) & station_ids(actor))


def _manage(actor: User, person: User, what: str) -> None:
    _require_role(actor, MANAGERS, what)
    if not manages(actor, person):
        raise Forbidden(f"You can {what} only for people below your role at your own stations")


def reset_password(session: Session, actor: User, user: User, reason: str) -> str:
    """Issue a new temporary password (returned once). The owner must replace it at their next login."""
    _manage(actor, user, "reset passwords")
    reason = _reason(reason)
    from app.auth.passwords import hash_password  # local: keeps this module's imports light

    temporary = new_temporary_password()
    user.password_hash = hash_password(temporary)
    user.must_change_password = True
    user.failed_logins, user.locked_until = 0, None
    _event(session, actor, user, AuthorizationChange.PASSWORD_RESET, None, None, reason)  # that it happened; never the password
    session.flush()
    return temporary


def set_active(session: Session, actor: User, user: User, active: bool, reason: str) -> User:
    """End (or restore) an account, for example when someone leaves. Nothing they did is touched: their work stays, attributed."""
    _manage(actor, user, "reactivate accounts" if active else "deactivate accounts")
    reason = _reason(reason)
    if user.is_active == active:
        raise Invalid(f"The account is already {'active' if active else 'deactivated'}")
    user.is_active = active
    _event(session, actor, user, AuthorizationChange.ACCOUNT_REACTIVATED if active else AuthorizationChange.ACCOUNT_DEACTIVATED,
           None, None, reason)
    session.flush()
    return user


# ---------------------------------------------------------------- stations


STATION_CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,15}$")


def create_station(session: Session, actor: User, *, code: str, name: str, district: str | None = None) -> PoliceStation:
    """Open a police station. Only the Super Admin does this. The code is permanent (cases and people refer to it)."""
    _require_role(actor, {OrgRole.SUPER_ADMIN}, "create police stations")
    code = (code or "").strip().upper()
    if not STATION_CODE.fullmatch(code):
        raise Invalid("The station code is 2 to 16 capital letters, digits or '-', for example PS-014")
    if not 3 <= len((name or "").strip()) <= 200:
        raise Invalid("Give the station's name (3 to 200 characters)")
    if session.scalar(select(PoliceStation.id).where(PoliceStation.organization_id == actor.organization_id, PoliceStation.code == code)):
        raise Conflict(f"A station with the code {code} already exists")
    station = PoliceStation(organization_id=actor.organization_id, code=code, name=name.strip(),
                            district=(district or "").strip() or None, created_by=actor.id)
    session.add(station)
    session.flush()
    return station


def update_station(session: Session, actor: User, station: PoliceStation, *, name: str, district: str | None, status: str) -> PoliceStation:
    """Correct a station's name or district, or mark it inactive (never deleted: its cases and history stay)."""
    _require_role(actor, {OrgRole.SUPER_ADMIN}, "change police stations")
    if station.organization_id != actor.organization_id:
        raise Invalid("Unknown police station")
    if not 3 <= len((name or "").strip()) <= 200:
        raise Invalid("Give the station's name (3 to 200 characters)")
    try:
        wanted = StationStatus(status)
    except ValueError:
        raise Invalid("The status is active or inactive") from None
    station.name, station.district, station.status = name.strip(), (district or "").strip() or None, wanted.value
    session.flush()
    return station
