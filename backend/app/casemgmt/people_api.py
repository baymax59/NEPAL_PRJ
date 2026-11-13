"""People and stations (phase R-4, docs/case-management/12-roles-and-stations.md): the register of officers, accounts, role changes,
station assignment, password resets and police stations. Every rule is in accounts.py and is checked there again for every
request; the listings (people.py) only tell the screens what to offer. Refusals are audited. Passwords are never recorded.
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.auth.mfa import require_strong_auth
from app.casemgmt import accounts, people
from app.casemgmt.api import Audit, Audited, CurrentUser, DbSession
from app.casemgmt.errors import Invalid

router = APIRouter(prefix="/v1/people", tags=["case management: people and stations"])
HANDOVER = ("This is a temporary password, shown only now. Give it to the person in private: they must choose their own at their "
            "first login. If it is lost, reset it.")
MAX_CSV_BYTES = 1_000_000


# ---------------------------------------------------------------- schemas


class StationBrief(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class OfficerBrief(BaseModel):
    officer_number: str
    full_name: str
    rank: str


class PersonCan(BaseModel):
    change_role: bool
    allowed_roles: list[str]  # the roles this viewer may give this person
    change_clearance: bool
    allowed_clearances: list[str]  # the clearances this viewer may give this person (never above their own)
    set_stations: bool
    reset_password: bool
    deactivate: bool
    reactivate: bool


class AccountRow(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    org_role: str
    clearance: str
    is_active: bool
    must_change_password: bool
    org_role_since: dt.datetime | None
    last_login_at: dt.datetime | None
    email: str | None
    phone: str | None
    job_title: str | None
    photo: int | None = None  # changes when the person's photo does; None: no photo
    officer: OfficerBrief | None
    stations: list[StationBrief]
    can: PersonCan


class Capabilities(BaseModel):
    role: str
    create_roles: list[str]  # the roles this person may create accounts for
    can_create_accounts: bool
    can_manage_people: bool  # change roles and stations, reset passwords, end accounts
    can_enter_officers: bool
    can_manage_stations: bool
    sees_people: bool


class AccountCreate(BaseModel):
    officer_number: str = Field(min_length=2, max_length=32)
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=3, max_length=128)
    role: str = Field(max_length=32)
    clearance: str = Field(max_length=16)
    extra_station_ids: list[uuid.UUID] = []  # only for an Administrator, who may have several stations


class AccountCreated(BaseModel):
    person: AccountRow
    temporary_password: str
    handover: str


class PasswordIssued(BaseModel):
    temporary_password: str
    handover: str


class RoleChange(BaseModel):
    role: str = Field(max_length=32)
    reason: str = Field(min_length=5, max_length=500)


class ClearanceChange(BaseModel):
    clearance: str = Field(max_length=16)
    reason: str = Field(min_length=5, max_length=500)


class StationsSet(BaseModel):
    station_ids: list[uuid.UUID] = Field(min_length=1)
    reason: str = Field(min_length=5, max_length=500)


class Reason(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class ActiveChange(BaseModel):
    active: bool
    reason: str = Field(min_length=5, max_length=500)


class AccountBrief(BaseModel):
    username: str
    display_name: str
    is_active: bool


class OfficerOut(BaseModel):
    id: uuid.UUID
    officer_number: str
    full_name: str
    rank: str
    station: StationBrief
    highest_role: str
    account: AccountBrief | None
    creatable_roles: list[str]  # the roles this viewer could give this officer (no account yet)


class OfficerCreate(BaseModel):
    officer_number: str = Field(min_length=2, max_length=32)
    full_name: str = Field(min_length=3, max_length=200)
    rank: str = Field(min_length=2, max_length=64)
    station_id: uuid.UUID
    highest_role: str = Field(max_length=32)


class ImportError_(BaseModel):
    row: int
    officer_number: str
    message: str


class ImportResult(BaseModel):
    imported: int
    errors: list[ImportError_]


class StationSummary(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    district: str | None
    status: str
    people: int
    officers: int
    cases: int
    open_cases: int


class StationCreate(BaseModel):
    code: str = Field(min_length=2, max_length=16)
    name: str = Field(min_length=3, max_length=200)
    district: str | None = Field(None, max_length=200)


class StationUpdate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    district: str | None = Field(None, max_length=200)
    status: str = Field(max_length=16)


# ---------------------------------------------------------------- what the screens may offer


@router.get("/capabilities", response_model=Capabilities)
def my_capabilities(user: CurrentUser) -> dict:
    return people.capabilities(user)


# ---------------------------------------------------------------- accounts


@router.get("/accounts", response_model=list[AccountRow])
def list_accounts(user: CurrentUser, db: DbSession, audit: Audit, q: Annotated[str | None, Query(max_length=100)] = None) -> list[dict]:
    with Audited(db, audit, user, "cm.people.list", "cm_user") as event:
        result = people.list_people(db, user, q=q)
        event.read(count=len(result))  # the search text itself is not recorded
    return result


@router.post("/accounts", response_model=AccountCreated, status_code=status.HTTP_201_CREATED)
def create_account(body: AccountCreate, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Make the account of a registered officer. A temporary password comes back once."""
    with Audited(db, audit, user, "cm.people.account_created", "cm_user", body.username.strip().lower(), role=body.role,
                 officer=body.officer_number.strip().upper()) as event:
        require_strong_auth(user, "creating accounts")
        created = accounts.create_account(db, user, officer_number=body.officer_number, username=body.username,
                                          display_name=body.display_name, role=body.role, clearance=body.clearance,
                                          extra_station_ids=body.extra_station_ids)
        result = {"person": people.person_row(db, user, created.user), "temporary_password": created.temporary_password, "handover": HANDOVER}
        event.write(user=created.user.username, role=created.user.org_role)  # never the password
    return result


@router.post("/accounts/{user_id}/role", response_model=AccountRow)
def change_role(user_id: uuid.UUID, body: RoleChange, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """A promotion or demotion. It adds no power over cases that already exist."""
    with Audited(db, audit, user, "cm.people.role_changed", "cm_user", user_id, role=body.role) as event:
        require_strong_auth(user, "changing roles")
        person = people.get_person(db, user, user_id)
        event.target_id = person.username
        old = person.org_role
        accounts.change_role(db, user, person, body.role, body.reason)
        result = people.person_row(db, user, person)
        event.write(old=old, new=person.org_role)
    return result


@router.post("/accounts/{user_id}/clearance", response_model=AccountRow)
def change_clearance(user_id: uuid.UUID, body: ClearanceChange, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Raise or lower what a person may see. Kept in the access history with the reason."""
    with Audited(db, audit, user, "cm.people.clearance_changed", "cm_user", user_id, clearance=body.clearance) as event:
        require_strong_auth(user, "changing clearances")
        person = people.get_person(db, user, user_id)
        event.target_id = person.username
        old = person.clearance
        accounts.change_clearance(db, user, person, body.clearance, body.reason)
        result = people.person_row(db, user, person)
        event.write(old=old, new=person.clearance)
    return result


@router.post("/accounts/{user_id}/stations", response_model=AccountRow)
def set_stations(user_id: uuid.UUID, body: StationsSet, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Set the stations a person works at (an Administrator: one or more; everybody else: exactly one)."""
    with Audited(db, audit, user, "cm.people.stations_set", "cm_user", user_id) as event:
        require_strong_auth(user, "assigning stations")
        person = people.get_person(db, user, user_id)
        event.target_id = person.username
        chosen = accounts.set_stations(db, user, person, body.station_ids, body.reason)
        result = people.person_row(db, user, person)
        event.write(stations=[s.code for s in chosen])
    return result


@router.post("/accounts/{user_id}/reset-password", response_model=PasswordIssued)
def reset_password(user_id: uuid.UUID, body: Reason, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """A new temporary password, shown once; the owner must replace it at their next login."""
    with Audited(db, audit, user, "cm.people.password_reset", "cm_user", user_id) as event:
        require_strong_auth(user, "resetting passwords")
        person = people.get_person(db, user, user_id)
        event.target_id = person.username
        temporary = accounts.reset_password(db, user, person, body.reason)
        event.write()  # that it happened, never the password
    return {"temporary_password": temporary, "handover": HANDOVER}


@router.post("/accounts/{user_id}/active", response_model=AccountRow)
def set_active(user_id: uuid.UUID, body: ActiveChange, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """End an account (someone leaves) or restore it. Their work stays, attributed to them."""
    with Audited(db, audit, user, "cm.people.account_active", "cm_user", user_id, active=body.active) as event:
        require_strong_auth(user, "ending accounts")
        person = people.get_person(db, user, user_id)
        event.target_id = person.username
        accounts.set_active(db, user, person, body.active, body.reason)
        result = people.person_row(db, user, person)
        event.write()
    return result


# ---------------------------------------------------------------- the register of officers


@router.get("/officers", response_model=list[OfficerOut])
def list_officers(user: CurrentUser, db: DbSession, audit: Audit, q: Annotated[str | None, Query(max_length=100)] = None,
                  free: bool = False, station_id: uuid.UUID | None = None) -> list[dict]:
    """The register as far as the viewer can reach. `free=true`: only officers who have no account yet."""
    with Audited(db, audit, user, "cm.people.officers", "cm_user") as event:
        result = people.list_officers(db, user, q=q, free_only=free, station_id=station_id)
        event.read(count=len(result))
    return result


@router.post("/officers", response_model=OfficerOut, status_code=status.HTTP_201_CREATED)
def add_officer(body: OfficerCreate, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Enter one officer in the register (the Super Admin only)."""
    with Audited(db, audit, user, "cm.people.officer_added", "cm_user", body.officer_number.strip().upper(), station=str(body.station_id)) as event:
        require_strong_auth(user, "entering officers")
        officer = accounts.add_officer(db, user, officer_number=body.officer_number, full_name=body.full_name, rank=body.rank,
                                       station_id=body.station_id, highest_role=body.highest_role)
        result = people.list_officers(db, user, q=officer.officer_number, station_id=officer.station_id)[0]
        event.write(officer=officer.officer_number)
    return result


@router.post("/officers/import", response_model=ImportResult)
def import_officers(user: CurrentUser, db: DbSession, audit: Audit, file: Annotated[UploadFile, File()]) -> dict:
    """Enter many officers from a CSV file. All or nothing: any problem is listed and nothing is entered."""
    with Audited(db, audit, user, "cm.people.officers_imported", "cm_user") as event:
        require_strong_auth(user, "entering officers")
        content = file.file.read(MAX_CSV_BYTES + 1)
        if len(content) > MAX_CSV_BYTES:
            raise Invalid("The file is larger than 1 MB")
        result = people.import_officers(db, user, content)
        event.write(imported=result["imported"], problems=len(result["errors"]))
    return result


# ---------------------------------------------------------------- stations


@router.get("/stations", response_model=list[StationSummary])
def list_stations(user: CurrentUser, db: DbSession, audit: Audit) -> list[dict]:
    """The stations the viewer can reach, with how many people, officers and cases each has."""
    with Audited(db, audit, user, "cm.people.stations", "cm_user") as event:
        result = people.station_summaries(db, user)
        event.read(count=len(result))
    return result


@router.post("/stations", response_model=StationSummary, status_code=status.HTTP_201_CREATED)
def create_station(body: StationCreate, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Open a police station (the Super Admin only). Stations are never deleted."""
    with Audited(db, audit, user, "cm.people.station_created", "cm_station", body.code.strip().upper()) as event:
        require_strong_auth(user, "creating police stations")
        station = accounts.create_station(db, user, code=body.code, name=body.name, district=body.district)
        result = next(s for s in people.station_summaries(db, user) if s["id"] == station.id)
        event.write(station=station.code)
    return result


@router.post("/stations/{station_id}", response_model=StationSummary)
def update_station(station_id: uuid.UUID, body: StationUpdate, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """Correct a station's name or district, or mark it inactive (the Super Admin only). Its history stays."""
    with Audited(db, audit, user, "cm.people.station_changed", "cm_station", station_id) as event:
        require_strong_auth(user, "changing police stations")
        station = people.get_station(db, user, station_id)
        event.target_id = station.code
        accounts.update_station(db, user, station, name=body.name, district=body.district, status=body.status)
        result = next(s for s in people.station_summaries(db, user) if s["id"] == station.id)
        event.write(status=station.status)
    return result
