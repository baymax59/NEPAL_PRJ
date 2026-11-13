"""Station and officer dashboards (phase R-5, docs/case-management/12-roles-and-stations.md §7). Read only.

Who sees what: a Super Admin every station and officer; an Administrator or Supervisor the stations they are assigned to and
the officers below them who work there; an Investigator only their own page. Anything outside that answers 404, like something
that doesn't exist. Every figure counts only the cases the viewer could open. See dashboards.py for the words used.
"""

import datetime as dt
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.casemgmt import dashboards
from app.casemgmt.api import Audit, Audited, CurrentUser, DbSession
from app.casemgmt.schemas import CaseRef

router = APIRouter(prefix="/v1/dashboards", tags=["case management: dashboards"])


class DashboardStation(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    district: str | None
    status: str


class DashboardStationBrief(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class OldestCase(BaseModel):
    case: CaseRef
    opened_at: dt.datetime
    days_open: int


class CaseFigures(BaseModel):
    total: int
    open: int  # not closed or archived; includes the pending ones
    closed: int  # closed or archived
    pending_evidence: int
    pending_review: int
    by_status: dict[str, int]
    new_this_month: int
    average_days_to_close: float | None  # of the cases now closed or archived; None when there are none
    oldest_open: list[OldestCase]


class OfficerCases(BaseModel):
    total: int
    open: int
    closed: int
    pending_evidence: int
    pending_review: int


class OfficerTasks(BaseModel):
    done: int
    open: int  # not finished, not yet due
    late: int  # not finished, past the due date


class OfficerWork(BaseModel):
    entries: int  # history entries they made: notes, exhibits, team changes...
    entries_last_30_days: int
    notes: int  # notes written or revised
    evidence: int  # exhibits added


class OfficerOfficial(BaseModel):
    officer_number: str
    full_name: str
    rank: str


class DashboardPerson(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    org_role: str
    is_active: bool
    officer: OfficerOfficial | None
    stations: list[DashboardStationBrief]


class OfficerFigures(BaseModel):
    cases: OfficerCases
    tasks: OfficerTasks
    work: OfficerWork
    last_activity: dt.datetime | None


class StationRow(BaseModel):
    station: DashboardStation
    figures: CaseFigures
    officers: int


class StationsOverview(BaseModel):
    stations: list[StationRow]
    generated_at: dt.datetime


class MonthRow(BaseModel):
    month: str  # "2026-11"
    opened: int
    closed: int


class OfficerRow(OfficerFigures):
    person: DashboardPerson


class StationDashboard(BaseModel):
    station: DashboardStation
    figures: CaseFigures
    monthly: list[MonthRow]
    officers: list[OfficerRow]
    generated_at: dt.datetime


class OfficerCase(BaseModel):
    case: CaseRef
    station_code: str
    roles: list[str]  # "lead", "contributor", "analyst", "viewer", "supervisor"
    active: bool  # still on the case; False: the work is credited to them but their access ended
    opened_at: dt.datetime
    days_open: int | None  # None once the case is closed


class OfficerDashboard(OfficerFigures):
    person: DashboardPerson
    case_list: list[OfficerCase]  # the cases behind `cases`, oldest first
    generated_at: dt.datetime


@router.get("/stations", response_model=StationsOverview)
def stations(user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.dashboard.stations", "cm_station") as event:
        result = dashboards.stations_overview(db, user)
        event.read(count=len(result["stations"]))
    return result


@router.get("/stations/{station_id}", response_model=StationDashboard)
def station(station_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.dashboard.station", "cm_station", station_id) as event:
        result = dashboards.station_dashboard(db, user, station_id)
        event.target_id = result["station"]["code"]
        event.read(officers=len(result["officers"]))
    return result


@router.get("/officers/{user_id}", response_model=OfficerDashboard)
def officer(user_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.dashboard.officer", "cm_user", user_id) as event:
        result = dashboards.officer_dashboard(db, user, user_id)
        event.target_id = result["person"]["username"]
        event.read(cases=len(result["case_list"]))
    return result
