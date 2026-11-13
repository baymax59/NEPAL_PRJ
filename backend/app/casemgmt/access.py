"""Who may see and do what in Case Management (docs/case-management/04 §6, 12 and 13).

As in Step 10, the rules are conditions inside the SQL of every query, never a filter applied afterwards.
Anything a user may not see answers exactly like something that doesn't exist (404).

A person sees a case if it is in their organisation and within their clearance and
- they are a Super Admin (every station), or
- they are an Administrator or Supervisor of the case's station (a Supervisor also of the cases assigned to them), or
- they are on the case's team (the Investigator who leads it, or a Sub Investigator, Analyst or Viewer added to it).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, and_, exists, false, or_, select, true
from sqlalchemy.orm import Session, object_session

from app.auth.access import sensitivities_up_to
from app.casemgmt.enums import FileStatus, MemberRole, OrgRole, WorkflowStatus
from app.casemgmt.errors import Forbidden, NotVisible
from app.casemgmt.models import Artifact, CaseFamily, CaseMember, EvidenceItem, UserStation
from app.db.models import User

WRITE_ROLES = {MemberRole.LEAD, MemberRole.SUB_INVESTIGATOR, MemberRole.ANALYST}
CASE_CREATORS = {OrgRole.SUPER_ADMIN, OrgRole.ADMINISTRATOR, OrgRole.SUPERVISOR, OrgRole.INVESTIGATOR}
LEAD_CAPABLE = {OrgRole.SUPER_ADMIN, OrgRole.ADMINISTRATOR, OrgRole.SUPERVISOR, OrgRole.INVESTIGATOR}
SUPERVISING = {OrgRole.SUPER_ADMIN, OrgRole.ADMINISTRATOR, OrgRole.SUPERVISOR}
# These roles see every case of their station(s). Everyone else sees only the cases they are on the team of
# (a Super Admin sees every case of the organisation).
STATION_WIDE = {OrgRole.ADMINISTRATOR, OrgRole.SUPERVISOR}


def my_stations(user: User):
    """A subquery of the stations the user is assigned to (never the revoked ones)."""
    return select(UserStation.station_id).where(UserStation.user_id == user.id, UserStation.revoked_at.is_(None))


def station_ids(user: User) -> set[uuid.UUID]:
    """The stations the user is assigned to. A Super Admin needs no assignment: see `works_at`."""
    session = object_session(user)
    return set(session.scalars(my_stations(user))) if session is not None else set()


def works_at(user: User, station_id) -> bool:
    """The user may work at / see this station: a Super Admin anywhere in the organisation, others where they are assigned."""
    if user.organization_id is None:
        return False
    return user.org_role == OrgRole.SUPER_ADMIN or station_id in station_ids(user)


def _on_team(user: User) -> ColumnElement[bool]:
    return exists().where(CaseMember.case_family_id == CaseFamily.id, CaseMember.user_id == user.id,
                          CaseMember.revoked_at.is_(None)).correlate(CaseFamily)  # only the case is the outer query's


def family_condition(user: User) -> ColumnElement[bool]:
    """The user's organisation, within their clearance. Every case query starts from this."""
    if user.organization_id is None:
        return false()
    return and_(
        CaseFamily.organization_id == user.organization_id,
        CaseFamily.classification.in_(list(sensitivities_up_to(user.clearance))),
    )


def case_condition(user: User) -> ColumnElement[bool]:
    """Cases the user may open (the query must select from CaseFamily).

    Super Admins: every case of their organisation. Administrators and Supervisors: every case of their station(s)
    (a Supervisor also the cases assigned to them). Everyone: the cases they are on the team of."""
    scope = [_on_team(user)]
    if user.org_role == OrgRole.SUPER_ADMIN:
        scope.append(true())
    elif user.org_role in STATION_WIDE:
        scope.append(CaseFamily.station_id.in_(my_stations(user)))
        if user.org_role == OrgRole.SUPERVISOR:
            scope.append(CaseFamily.supervisor_id == user.id)
    return and_(family_condition(user), or_(*scope))


def get_family(session: Session, user: User, family_id) -> CaseFamily:
    """A case the user may open, or NotVisible (404) whatever the reason."""
    family = session.scalar(select(CaseFamily).where(CaseFamily.id == family_id, case_condition(user)))
    if family is None:
        raise NotVisible(exists=session.get(CaseFamily, family_id) is not None)
    return family


def membership(session: Session, user: User, family: CaseFamily) -> CaseMember | None:
    """The user's active place on the case's team, if any."""
    return session.scalar(
        select(CaseMember).where(CaseMember.case_family_id == family.id, CaseMember.user_id == user.id, CaseMember.revoked_at.is_(None))
    )


def member_role(session: Session, user: User, family: CaseFamily) -> MemberRole | None:
    member = membership(session, user, family)
    return MemberRole(member.role) if member else None


def is_case_lead(session: Session, user: User, family: CaseFamily) -> bool:
    """The user is the Investigator who leads the case."""
    return member_role(session, user, family) == MemberRole.LEAD


def powers_reach(user: User, family: CaseFamily) -> bool:
    """A promotion adds no power over cases that already exist (docs/case-management/12 section 5): powers that come
    from the role itself reach only cases registered since the role took effect. Seeing them is not affected."""
    return user.org_role_since is None or family.created_at >= user.org_role_since


def supervises(user: User, family: CaseFamily) -> bool:
    """May oversee the case (seal, decide its closing, hand it over, add folders; sees withdrawn files, highlighted): the Super Admin of its
    organisation, an Administrator of its station, or the Supervisor assigned to it. The first two only for cases registered
    since their role took effect; being assigned to a case is an explicit act and always counts."""
    if user.organization_id is None or user.organization_id != family.organization_id:
        return False
    if family.supervisor_id == user.id and user.org_role in SUPERVISING:
        return True  # assigned to the case (also after a promotion: nothing is taken away, nothing is added)
    if user.org_role == OrgRole.SUPERVISOR:
        return False
    if not powers_reach(user, family):
        return False
    if user.org_role == OrgRole.SUPER_ADMIN:
        return True
    return user.org_role == OrgRole.ADMINISTRATOR and family.station_id in station_ids(user)


@dataclass(frozen=True)
class Rights:
    """What one person may do in one case (docs/case-management/13 §3). `role` is their part on the team, if any;
    `oversees` is the Supervisor / Administrator / Super Admin power; `open` is False once the case is archived."""

    role: MemberRole | None
    oversees: bool
    open: bool

    @property
    def add_files(self) -> bool:
        return self.open and (self.role in WRITE_ROLES or self.oversees)

    @property
    def revise_any(self) -> bool:
        return self.open and (self.role == MemberRole.LEAD or self.oversees)

    @property
    def withdraw(self) -> bool:
        """Only the Investigator who leads the case withdraws a file. Whoever oversees the case (Supervisor, Administrator,
        Super Admin) keeps every withdrawn file in view, highlighted, and removes nothing."""
        return self.open and self.role == MemberRole.LEAD

    @property
    def rename_case(self) -> bool:
        """Change the case number: only whoever oversees the case (Supervisor, Administrator, Super Admin), while it is open."""
        return self.open and self.oversees

    @property
    def add_folders(self) -> bool:
        return self.revise_any

    @property
    def manage_team(self) -> bool:
        return self.revise_any

    @property
    def create_tasks(self) -> bool:
        return self.add_files

    @property
    def assign_tasks(self) -> bool:
        return self.revise_any

    @property
    def comment(self) -> bool:
        return self.add_files  # viewers read comments but don't write them


def rights(session: Session, user: User, family: CaseFamily) -> Rights:
    return Rights(member_role(session, user, family), supervises(user, family), family.workflow_status != WorkflowStatus.ARCHIVED.value)


def require(allowed: bool, what: str, found: Rights) -> None:
    """Refuse (403) with the reason a person can act on."""
    if allowed:
        return
    if not found.open:
        raise Forbidden("This case is archived: its record is preserved and can't change")
    raise Forbidden(what)


def is_super_admin(user: User) -> bool:
    return user.org_role == OrgRole.SUPER_ADMIN and user.organization_id is not None


def sees_family(user: User, family: CaseFamily) -> bool:
    """The case is in the user's organisation and within their clearance (the start of every access decision)."""
    return (user.organization_id is not None and family.organization_id == user.organization_id
            and family.classification in sensitivities_up_to(user.clearance))


def may_see_item(user: User, family: CaseFamily, item: EvidenceItem) -> bool:
    """Sealed evidence: only the case's supervisor and administrators. Every item: enough clearance. A withdrawn exhibit has
    left the team's view: only those who oversee the case still see it (highlighted)."""
    if item.classification not in sensitivities_up_to(user.clearance):
        return False
    if item.status == FileStatus.WITHDRAWN.value and not supervises(user, family):
        return False
    return not item.sealed or supervises(user, family)


def hidden_file_ids(session: Session, user: User, family: CaseFamily) -> set[uuid.UUID]:
    """Ids of the files of the case the user may not see: sealed or too highly classified evidence, sealed notes and analyses.

    They are left out of every view as if they weren't there. Withdrawn files are hidden the same way from everyone who doesn't oversee the case."""
    hidden: set[uuid.UUID] = {
        item.id for item in session.scalars(select(EvidenceItem).where(EvidenceItem.case_family_id == family.id))
        if not may_see_item(user, family, item)
    }
    if not supervises(user, family):
        hidden |= set(session.scalars(select(Artifact.id).where(Artifact.case_family_id == family.id, Artifact.sealed.is_(True))))
        hidden |= set(session.scalars(select(Artifact.id).where(Artifact.case_family_id == family.id,
                                                                Artifact.status == FileStatus.WITHDRAWN.value)))
    return hidden
