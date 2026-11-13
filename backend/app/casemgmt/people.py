"""What the "People & stations" screens list: the people, the register of officers and the stations a person can reach, with
what the viewer may do about each (docs/case-management/12-roles-and-stations.md). The rules themselves are in accounts.py;
every action is checked there again, whatever the screen offered."""

import csv
import io
import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.auth.access import SENSITIVITY_ORDER, sensitivities_up_to
from app.auth.photos import version as photo_version
from app.casemgmt import accounts
from app.casemgmt.access import station_ids
from app.casemgmt.accounts import CREATABLE, MANAGERS, RANK, SEVERAL_STATIONS
from app.casemgmt.enums import OrgRole, StationStatus, WorkflowStatus
from app.casemgmt.errors import CaseManagementError, Forbidden, Invalid, NotVisible
from app.casemgmt.models import CaseFamily, OfficerRegistry, PoliceStation, UserStation
from app.db.models import User

MAX_IMPORT_ROWS = 2000
IMPORT_COLUMNS = ("officer_number", "full_name", "rank", "station_code", "highest_role")
CLOSED = {WorkflowStatus.CLOSED.value, WorkflowStatus.ARCHIVED.value}


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _creator_roles(actor: User) -> list[str]:
    return [r.value for r in sorted(CREATABLE.get(OrgRole(actor.org_role), set()), key=RANK.get)]


def capabilities(actor: User) -> dict:
    """What the screens may offer this person (the backend checks every request again)."""
    role = OrgRole(actor.org_role)
    return {
        "role": role.value,
        "create_roles": _creator_roles(actor),
        "can_create_accounts": role in CREATABLE,
        "can_manage_people": role in MANAGERS,
        "can_enter_officers": role == OrgRole.SUPER_ADMIN,
        "can_manage_stations": role == OrgRole.SUPER_ADMIN,
        "sees_people": role in CREATABLE or role in MANAGERS,
    }


def _require_to_see(actor: User) -> None:
    if actor.organization_id is None or not (OrgRole(actor.org_role) in CREATABLE):
        raise Forbidden("Your role doesn't list people")


# ---------------------------------------------------------------- stations


def _station_brief(station: PoliceStation) -> dict:
    return {"id": station.id, "code": station.code, "name": station.name}


def station_summaries(session: Session, actor: User) -> list[dict]:
    """The stations the actor can reach (a Super Admin: all), with how many people, officers and cases each has."""
    _require_to_see(actor)
    query = select(PoliceStation).where(PoliceStation.organization_id == actor.organization_id)
    if actor.org_role != OrgRole.SUPER_ADMIN:
        query = query.where(PoliceStation.id.in_(station_ids(actor)))
    stations = list(session.scalars(query.order_by(PoliceStation.code)))
    ids = [s.id for s in stations]
    people = dict(session.execute(select(UserStation.station_id, func.count()).join(User, User.id == UserStation.user_id).where(
        UserStation.station_id.in_(ids), UserStation.revoked_at.is_(None), User.is_active.is_(True)).group_by(UserStation.station_id)).all())
    officers = dict(session.execute(select(OfficerRegistry.station_id, func.count()).where(
        OfficerRegistry.station_id.in_(ids)).group_by(OfficerRegistry.station_id)).all())
    cases = {sid: (total, open_) for sid, total, open_ in session.execute(select(
        CaseFamily.station_id, func.count(), func.count().filter(CaseFamily.workflow_status.not_in(CLOSED))).where(
        CaseFamily.station_id.in_(ids)).group_by(CaseFamily.station_id)).all()}
    return [{"id": s.id, "code": s.code, "name": s.name, "district": s.district, "status": s.status,
             "people": people.get(s.id, 0), "officers": officers.get(s.id, 0),
             "cases": cases.get(s.id, (0, 0))[0], "open_cases": cases.get(s.id, (0, 0))[1]} for s in stations]


def get_station(session: Session, actor: User, station_id: uuid.UUID) -> PoliceStation:
    station = session.get(PoliceStation, station_id)
    if station is None or station.organization_id != actor.organization_id:
        raise NotVisible()
    if actor.org_role != OrgRole.SUPER_ADMIN and station.id not in station_ids(actor):
        raise NotVisible(exists=True)
    return station


# ---------------------------------------------------------------- the register of officers


def _officer_row(officer: OfficerRegistry, station: PoliceStation, account: User | None, actor: User) -> dict:
    highest = RANK[OrgRole(officer.highest_role)]
    return {
        "id": officer.id, "officer_number": officer.officer_number, "full_name": officer.full_name, "rank": officer.rank,
        "station": _station_brief(station), "highest_role": officer.highest_role,
        "account": {"username": account.username, "display_name": account.display_name, "is_active": account.is_active} if account else None,
        # the roles this viewer could give this officer (only while the officer has no account)
        "creatable_roles": [r for r in _creator_roles(actor) if RANK[OrgRole(r)] <= highest] if account is None else [],
    }


def list_officers(session: Session, actor: User, *, q: str | None = None, free_only: bool = False, station_id: uuid.UUID | None = None,
                  limit: int = 300) -> list[dict]:
    """Officers of the register the viewer can reach: every station for a Super Admin, else their own station(s)."""
    _require_to_see(actor)
    query = (select(OfficerRegistry, PoliceStation, User)
             .join(PoliceStation, PoliceStation.id == OfficerRegistry.station_id)
             .outerjoin(User, User.officer_id == OfficerRegistry.id)
             .where(OfficerRegistry.organization_id == actor.organization_id))
    if actor.org_role != OrgRole.SUPER_ADMIN:
        query = query.where(OfficerRegistry.station_id.in_(station_ids(actor)))
    if station_id is not None:
        query = query.where(OfficerRegistry.station_id == station_id)
    if free_only:
        query = query.where(User.id.is_(None))
    if q and q.strip():
        pattern = _like(q.strip())
        query = query.where(or_(OfficerRegistry.officer_number.ilike(pattern, escape="\\"), OfficerRegistry.full_name.ilike(pattern, escape="\\")))
    rows = session.execute(query.order_by(PoliceStation.code, OfficerRegistry.officer_number).limit(limit)).all()
    return [_officer_row(o, s, u, actor) for o, s, u in rows]


def import_officers(session: Session, actor: User, content: bytes) -> dict:
    """Enter many officers from a CSV file (columns: officer_number, full_name, rank, station_code, highest_role).
    All or nothing: if any row has a problem nothing is entered, and every problem is listed."""
    if actor.org_role != OrgRole.SUPER_ADMIN:
        raise Forbidden("Only the Super Admin enters officers in the register")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Invalid("The file must be a CSV saved as UTF-8") from None
    reader = csv.DictReader(io.StringIO(text))
    header = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in IMPORT_COLUMNS if c not in header]
    if missing:
        raise Invalid("The first row must name the columns: " + ", ".join(IMPORT_COLUMNS) + " (missing: " + ", ".join(missing) + ")")
    reader.fieldnames = header
    rows = list(reader)
    if not rows:
        raise Invalid("The file has no officers")
    if len(rows) > MAX_IMPORT_ROWS:
        raise Invalid(f"At most {MAX_IMPORT_ROWS} officers per file")
    by_code = {s.code: s for s in session.scalars(select(PoliceStation).where(PoliceStation.organization_id == actor.organization_id))}
    errors: list[dict] = []
    nested = session.begin_nested()
    for number, row in enumerate(rows, start=2):  # row 1 is the header
        station = by_code.get((row.get("station_code") or "").strip().upper())
        try:
            if station is None:
                raise Invalid(f"Unknown station code '{(row.get('station_code') or '').strip()}'")
            accounts.add_officer(session, actor, officer_number=row.get("officer_number") or "", full_name=row.get("full_name") or "",
                                 rank=row.get("rank") or "", station_id=station.id, highest_role=(row.get("highest_role") or "").strip().lower())
        except CaseManagementError as error:
            errors.append({"row": number, "officer_number": (row.get("officer_number") or "").strip(), "message": str(error)})
    if errors:
        nested.rollback()
        return {"imported": 0, "errors": errors}
    nested.commit()
    return {"imported": len(rows), "errors": []}


# ---------------------------------------------------------------- people


def _person_row(actor: User, person: User, stations: list[PoliceStation], officer: OfficerRegistry | None) -> dict:
    actor_role, person_role = OrgRole(actor.org_role), OrgRole(person.org_role)
    manage = accounts.manages(actor, person)
    highest = RANK[OrgRole(officer.highest_role)] if officer else None
    roles = [r.value for r in sorted(RANK, key=RANK.get)
             if r != OrgRole.SUPER_ADMIN and r != person_role and RANK[r] < RANK[actor_role] and (highest is None or RANK[r] <= highest)] if manage else []
    levels = [s for s in SENSITIVITY_ORDER if s in sensitivities_up_to(actor.clearance) and s != person.clearance] if manage else []
    if actor_role == OrgRole.SUPER_ADMIN:
        can_stations = manage and person_role == OrgRole.ADMINISTRATOR
    else:
        can_stations = manage and actor_role == OrgRole.ADMINISTRATOR and person_role not in SEVERAL_STATIONS
    return {
        "id": person.id, "username": person.username, "display_name": person.display_name, "org_role": person.org_role,
        "clearance": person.clearance, "is_active": person.is_active, "must_change_password": person.must_change_password,
        "org_role_since": person.org_role_since, "last_login_at": person.last_login_at,
        "email": person.email, "phone": person.phone, "job_title": person.job_title, "photo": photo_version(person.photo_updated_at),
        "officer": {"officer_number": officer.officer_number, "full_name": officer.full_name, "rank": officer.rank} if officer else None,
        "stations": [_station_brief(s) for s in stations],
        "can": {"change_role": bool(roles), "allowed_roles": roles, "change_clearance": bool(levels), "allowed_clearances": levels, "set_stations": can_stations,
                "reset_password": manage and person.is_active, "deactivate": manage and person.is_active, "reactivate": manage and not person.is_active},
    }


def list_people(session: Session, actor: User, *, q: str | None = None, limit: int = 300) -> list[dict]:
    """The people the viewer can see: everyone for a Super Admin, else those at their own station(s)."""
    _require_to_see(actor)
    query = select(User).where(User.organization_id == actor.organization_id)
    if actor.org_role != OrgRole.SUPER_ADMIN:
        query = query.where(or_(User.id == actor.id, User.id.in_(select(UserStation.user_id).where(
            UserStation.revoked_at.is_(None), UserStation.station_id.in_(station_ids(actor))))))
    if q and q.strip():
        pattern = _like(q.strip())
        query = query.where(or_(User.display_name.ilike(pattern, escape="\\"), User.username.ilike(pattern, escape="\\")))
    people = list(session.scalars(query.order_by(User.display_name, User.username).limit(limit)))
    ids = [p.id for p in people]
    stations: dict[uuid.UUID, list[PoliceStation]] = {}
    for user_id, station in session.execute(select(UserStation.user_id, PoliceStation).join(PoliceStation, PoliceStation.id == UserStation.station_id).where(
            UserStation.user_id.in_(ids), UserStation.revoked_at.is_(None)).order_by(PoliceStation.code)):
        stations.setdefault(user_id, []).append(station)
    officers = {o.id: o for o in session.scalars(select(OfficerRegistry).where(OfficerRegistry.id.in_([p.officer_id for p in people if p.officer_id])))}
    return [_person_row(actor, p, stations.get(p.id, []), officers.get(p.officer_id)) for p in people]


def get_person(session: Session, actor: User, user_id: uuid.UUID) -> User:
    """A person the viewer can see (else "not found", as for someone who doesn't exist)."""
    person = session.get(User, user_id)
    if person is None or person.organization_id != actor.organization_id:
        raise NotVisible()
    if actor.org_role != OrgRole.SUPER_ADMIN and person.id != actor.id and not (station_ids(person) & station_ids(actor)):
        raise NotVisible(exists=True)
    return person


def person_row(session: Session, actor: User, person: User) -> dict:
    stations = list(session.scalars(select(PoliceStation).join(UserStation, UserStation.station_id == PoliceStation.id).where(
        UserStation.user_id == person.id, UserStation.revoked_at.is_(None)).order_by(PoliceStation.code)))
    officer = session.get(OfficerRegistry, person.officer_id) if person.officer_id else None
    return _person_row(actor, person, stations, officer)
