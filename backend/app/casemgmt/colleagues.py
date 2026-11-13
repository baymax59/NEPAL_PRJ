"""Choosing colleagues by name (spec §12 step 2, "searches for an existing authorized user"; §6 step 7).

Three purposes: the lead investigator or the supervisor of a case being registered, and someone to add to a case's
team. Only people the chooser could actually pick are listed: active users of the same organisation,
with a suitable role and enough clearance for the case. Only what is needed to choose is shown (name, user
name, organisation role); clearance levels are not. The backend checks everything again when the choice is
submitted, so this list is a convenience, not a permission.
"""

from typing import Literal

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.auth.access import sensitivities_up_to
from app.casemgmt.access import CASE_CREATORS, LEAD_CAPABLE, SUPERVISING, rights, station_ids
from app.casemgmt.enums import OrgRole
from app.casemgmt.errors import Forbidden, Invalid
from app.casemgmt.members import ROLES_FOR
from app.casemgmt.models import CaseFamily, CaseMember, UserStation
from app.core.enums import Sensitivity
from app.db.models import User

Purpose = Literal["lead", "supervisor", "team"]


def cleared_for(classification: str) -> list[str]:
    """The clearances that may see a case of this classification."""
    return [c.value for c in Sensitivity if classification in sensitivities_up_to(c.value)]


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def candidates(session: Session, actor: User, purpose: Purpose, *, classification: str | None = None,
               family: CaseFamily | None = None, q: str | None = None, limit: int = 20, station_id=None) -> list[dict]:
    if actor.organization_id is None:
        raise Forbidden("Your account isn't part of an organisation")
    conditions = [User.organization_id == actor.organization_id, User.is_active.is_(True)]
    if purpose in ("lead", "supervisor"):
        if actor.org_role not in CASE_CREATORS:
            raise Forbidden("Your role can't register cases")
        if classification not in {s.value for s in Sensitivity}:
            raise Invalid("Choose the case's classification first")
        roles = LEAD_CAPABLE if purpose == "lead" else SUPERVISING
        conditions.append(User.org_role.in_([r.value for r in roles]))
    elif purpose == "team":
        if family is None:
            raise Invalid("Which case is the person for?")
        if not rights(session, actor, family).manage_team:
            raise Forbidden("Only the Investigator who leads the case, its supervisor or an administrator can add people")
        classification = family.classification
        conditions += [
            User.id != actor.id,
            ~exists().where(CaseMember.case_family_id == family.id, CaseMember.user_id == User.id, CaseMember.revoked_at.is_(None)),
        ]
    else:
        raise Invalid("Unknown purpose: use lead, supervisor or team")
    conditions.append(User.clearance.in_(cleared_for(classification)))
    # Only people who work at the case's station (or, before a case exists, at the station asked for, else the actor's own).
    if family is not None:
        stations = {family.station_id}
    elif station_id is not None:
        stations = {station_id}
    else:
        stations = station_ids(actor)
    if actor.org_role != OrgRole.SUPER_ADMIN or family is not None or station_id is not None:
        at_station = exists().where(UserStation.user_id == User.id, UserStation.revoked_at.is_(None), UserStation.station_id.in_(stations))
        conditions.append(or_(User.org_role == OrgRole.SUPER_ADMIN.value, at_station))
    if q and q.strip():
        conditions.append(or_(User.display_name.ilike(_like(q.strip()), escape="\\"), User.username.ilike(_like(q.strip()), escape="\\")))
    users = list(session.scalars(select(User).where(*conditions).order_by(User.display_name, User.username).limit(limit)))

    result = []
    for user in users:
        roles = sorted(r.value for r in ROLES_FOR.get(OrgRole(user.org_role), set())) if purpose == "team" else []
        result.append({"id": user.id, "username": user.username, "display_name": user.display_name, "org_role": user.org_role,
                       "roles": roles})
    return result
