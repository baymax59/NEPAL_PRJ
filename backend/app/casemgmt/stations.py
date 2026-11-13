"""Police stations (docs/case-management/12-roles-and-stations.md): which stations a person may work at, and where a new
case is registered. Who may see a station's cases is decided in access.py."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casemgmt.access import my_stations
from app.casemgmt.enums import OrgRole, StationStatus
from app.casemgmt.errors import Forbidden, Invalid
from app.casemgmt.models import PoliceStation
from app.db.models import User

DEFAULT_CODE = "HQ"


def default_station(session: Session, organization_id: uuid.UUID) -> PoliceStation | None:
    """The organisation's default station (HQ, made by migration 0016), else its oldest active one."""
    stations = select(PoliceStation).where(PoliceStation.organization_id == organization_id,
                                           PoliceStation.status == StationStatus.ACTIVE.value)
    return (session.scalar(stations.where(PoliceStation.code == DEFAULT_CODE))
            or session.scalars(stations.order_by(PoliceStation.created_at)).first())


def usable_stations(session: Session, actor: User) -> list[PoliceStation]:
    """The active stations the actor may register cases at: every station for a Super Admin, else their own."""
    query = select(PoliceStation).where(PoliceStation.organization_id == actor.organization_id,
                                        PoliceStation.status == StationStatus.ACTIVE.value)
    if actor.org_role != OrgRole.SUPER_ADMIN:
        query = query.where(PoliceStation.id.in_(my_stations(actor)))
    return list(session.scalars(query.order_by(PoliceStation.created_at, PoliceStation.code)))


def station_for_new_case(session: Session, actor: User, station_id: uuid.UUID | None) -> PoliceStation:
    """The station a new case belongs to: the one asked for, or the actor's only one (a Super Admin: the default)."""
    allowed = usable_stations(session, actor)
    if station_id is None:
        if len(allowed) == 1:
            return allowed[0]
        if actor.org_role == OrgRole.SUPER_ADMIN and (default := default_station(session, actor.organization_id)) is not None:
            return default
        if not allowed:
            raise Forbidden("You are not assigned to a police station, so you can't register cases")
        raise Invalid("Choose the police station of the case")
    station = session.get(PoliceStation, station_id)
    if station is None or station.organization_id != actor.organization_id:
        raise Invalid("Unknown police station")  # the same answer for another organisation's station: nothing leaks
    if station.status != StationStatus.ACTIVE.value:
        raise Invalid(f"Station {station.code} is inactive: new cases can't be registered there")
    if station.id not in {s.id for s in allowed}:
        raise Forbidden(f"You can register cases only at your own police station(s), not at {station.code}")
    return station
