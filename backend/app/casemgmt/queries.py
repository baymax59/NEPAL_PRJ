"""Read-only views for the API: case lists, a case, my cases, and the admin registry (docs/case-management/13).

Every query starts from the access conditions in access.py (inside the SQL); nothing is filtered afterwards.
"""

import uuid
from collections import defaultdict

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.access import sensitivities_up_to
from app.auth.photos import version as photo_version
from app.casemgmt import history, members
from app.casemgmt.access import case_condition, family_condition, hidden_file_ids, rights, supervises
from app.casemgmt.case_types import case_type
from app.casemgmt.enums import FileStatus, MemberRole, StatusField
from app.casemgmt.models import (
    Artifact,
    CaseEntry,
    CaseFamily,
    CaseFolder,
    CaseMember,
    CaseNumberChange,
    CaseOfficialReference,
    CaseStatusEvent,
    EvidenceItem,
    PoliceStation,
)
from app.casemgmt.plain import plain
from app.db.models import User


def _like(text: str) -> str:
    """A LIKE pattern that matches the text literally (with escape='\\')."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def people(session: Session, ids) -> dict[uuid.UUID, dict]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: {"id": u.id, "username": u.username, "display_name": u.display_name, "photo": photo_version(u.photo_updated_at)}
            for u in session.scalars(select(User).where(User.id.in_(ids)))}


def case_ref(family: CaseFamily) -> dict:
    return {"id": family.id, "display_id": family.display_id, "title": family.title, "case_type": family.case_type,
            "priority": family.priority, "classification": family.classification, "workflow_status": family.workflow_status}


def _references(session: Session, family_ids) -> dict[uuid.UUID, list[CaseOfficialReference]]:
    found = defaultdict(list)
    for ref in session.scalars(select(CaseOfficialReference).where(CaseOfficialReference.case_family_id.in_(family_ids))
                               .order_by(CaseOfficialReference.recorded_at)):
        found[ref.case_family_id].append(ref)
    return found


def reference_label(ref: CaseOfficialReference) -> str:
    return f"{ref.ref_type} {ref.number}" + (f", {ref.issuing_authority}" if ref.issuing_authority else "")


def last_activity(session: Session, family_ids) -> dict:
    """The time of the latest history entry of each case."""
    ids = list(family_ids)
    if not ids:
        return {}
    return dict(session.execute(select(CaseEntry.case_family_id, func.max(CaseEntry.at))
                                .where(CaseEntry.case_family_id.in_(ids)).group_by(CaseEntry.case_family_id)).all())


def _my_roles(session: Session, user: User, family_ids) -> dict[uuid.UUID, str]:
    ids = list(family_ids)
    if not ids:
        return {}
    return dict(session.execute(select(CaseMember.case_family_id, CaseMember.role).where(
        CaseMember.user_id == user.id, CaseMember.revoked_at.is_(None), CaseMember.case_family_id.in_(ids))).all())


# ---------------------------------------------------------------- cases


def _matches_text(q: str):
    """The words typed in a case search: in the title, in the case number, or in a number the case had before."""
    return or_(CaseFamily.title.ilike(_like(q), escape="\\"), CaseFamily.display_id.ilike(_like(q), escape="\\"),
               CaseFamily.id.in_(select(CaseNumberChange.case_family_id).where(CaseNumberChange.old_number.ilike(_like(q), escape="\\"))))


def summary(family: CaseFamily, references: list[CaseOfficialReference], role: str | None, activity) -> dict:
    return {**case_ref(family), "case_type_label": case_type(family.case_type)["label"], "official_status": family.official_status,
            "created_at": family.created_at, "official_references": [reference_label(r) for r in references],
            "my_role": role, "last_activity": activity}


def list_cases(session: Session, user: User, *, limit: int, offset: int, q: str | None = None,
               workflow_status: str | None = None, case_type_code: str | None = None) -> tuple[list[dict], int]:
    """Cases the user may open, newest first."""
    conditions = [case_condition(user)]
    if q:
        conditions.append(_matches_text(q))
    if workflow_status:
        conditions.append(CaseFamily.workflow_status == workflow_status)
    if case_type_code:
        conditions.append(CaseFamily.case_type == case_type_code)
    total = session.scalar(select(func.count()).select_from(CaseFamily).where(*conditions))
    families = list(session.scalars(select(CaseFamily).where(*conditions)
                                    .order_by(CaseFamily.created_at.desc(), CaseFamily.id).limit(limit).offset(offset)))
    ids = [f.id for f in families]
    references, roles, activity = _references(session, ids), _my_roles(session, user, ids), last_activity(session, ids)
    return [summary(f, references.get(f.id, []), roles.get(f.id), activity.get(f.id)) for f in families], total


def team_rows(session: Session, family: CaseFamily, *, active_only: bool = False) -> list[dict]:
    rows = members.team(session, family)
    if active_only:
        rows = [r for r in rows if r[0].revoked_at is None]
    who = people(session, [u for m, _ in rows for u in (m.user_id, m.granted_by, m.revoked_by)])
    return [{"user": who.get(m.user_id), "role": m.role, "granted_by": who.get(m.granted_by), "granted_at": m.granted_at,
             "revoked_by": who.get(m.revoked_by), "revoked_at": m.revoked_at} for m, _ in rows]


def folders_of(session: Session, user: User, family: CaseFamily, hidden: set | None = None) -> list[dict]:
    """The case's folders, in the order they were made, with how many files in each the user can see."""
    hidden = hidden_file_ids(session, user, family) if hidden is None else hidden
    counts: dict[uuid.UUID, int] = defaultdict(int)
    for model in (Artifact, EvidenceItem):
        for folder_id, item_id in session.execute(select(model.folder_id, model.id).where(
                model.case_family_id == family.id, model.status == FileStatus.ACTIVE.value)):
            if item_id not in hidden:
                counts[folder_id] += 1
    folders = session.scalars(select(CaseFolder).where(CaseFolder.case_family_id == family.id).order_by(CaseFolder.added_at, CaseFolder.name))
    return [{"id": f.id, "name": f.name, "system": f.system, "files": counts.get(f.id, 0), "added_at": f.added_at} for f in folders]


def reported_by(family: CaseFamily) -> dict | None:
    """Who reported the case: None when nothing was recorded."""
    details = {k: getattr(family, f"reported_by_{k}") for k in ("name", "phone", "email", "address")}
    if not family.reported_by_unknown and not any(details.values()):
        return None
    return {"unknown": family.reported_by_unknown, **details}


def case_detail(session: Session, user: User, family: CaseFamily) -> dict:
    references = _references(session, [family.id]).get(family.id, [])
    events = list(session.scalars(select(CaseStatusEvent).where(
        CaseStatusEvent.case_family_id == family.id,
        CaseStatusEvent.field.in_([StatusField.WORKFLOW.value, StatusField.OFFICIAL.value])).order_by(CaseStatusEvent.id)))
    team = team_rows(session, family, active_only=True)
    lead = next((m["user"] for m in team if m["role"] == MemberRole.LEAD.value), None)
    renumbered = list(session.scalars(select(CaseNumberChange).where(CaseNumberChange.case_family_id == family.id).order_by(CaseNumberChange.id)))
    who = people(session, [family.supervisor_id, family.created_by, *(r.recorded_by for r in references), *(e.actor_id for e in events),
                           *(c.changed_by for c in renumbered)])
    found = rights(session, user, family)
    oversees = supervises(user, family)
    return {
        **summary(family, references, found.role.value if found.role else None, last_activity(session, [family.id]).get(family.id)),
        "description": family.description, "description_html": family.description_html, "reported_by": reported_by(family), "jurisdiction": family.jurisdiction,
        "supervisor": who.get(family.supervisor_id), "created_by": who.get(family.created_by), "lead": lead,
        "references": [{"id": r.id, "ref_type": r.ref_type, "number": r.number, "issuing_authority": r.issuing_authority,
                        "ref_date": r.ref_date, "source": r.source, "recorded_by": who.get(r.recorded_by),
                        "recorded_at": r.recorded_at} for r in references],
        "status_history": [{"field": e.field, "old_value": e.old_value, "new_value": e.new_value, "reason": plain(e.reason),
                            "actor": who.get(e.actor_id), "at": e.at} for e in events],
        "folders": folders_of(session, user, family), "team": team,
        "previous_numbers": [{"old_number": c.old_number, "new_number": c.new_number, "reason": c.reason, "changed_by": who.get(c.changed_by),
                              "changed_at": c.changed_at} for c in renumbered],
        "can": {"rename_case": found.rename_case, "change_workflow_status": oversees or found.role == MemberRole.LEAD, "change_official_status": oversees,
                "add_official_reference": oversees, "add_files": found.add_files, "add_folders": found.add_folders,
                "withdraw": found.withdraw, "manage_team": found.manage_team, "hand_over": oversees and found.open,
                "create_tasks": found.create_tasks, "comment": found.comment,
                "chat": found.role is not None, "write_chat": found.role is not None and found.open},
    }


def my_cases(session: Session, user: User) -> list[dict]:
    """The cases the user is on the team of, with their part: the Investigator's dashboard."""
    rows = session.execute(
        select(CaseMember, CaseFamily).join(CaseFamily, CaseFamily.id == CaseMember.case_family_id)
        .where(CaseMember.user_id == user.id, CaseMember.revoked_at.is_(None), family_condition(user))
        .order_by(CaseMember.granted_at.desc())).all()
    activity = last_activity(session, [f.id for _, f in rows])
    return [{"case": case_ref(f), "role": m.role, "active_from": m.granted_at, "last_activity": activity.get(f.id)} for m, f in rows]


def history_view(session: Session, family: CaseFamily, *, limit: int, after: int | None, latest: int | None = None) -> dict:
    if latest:  # the newest few, for "recent activity"
        rows, next_after = history.latest_entries(session, family.id, latest), None
    else:
        rows, next_after = history.entries(session, family.id, limit=limit, after_seq=after)
    who = people(session, [e.actor_id for e in rows])
    names = {i: p["display_name"] for i, p in who.items()}
    return {"case": case_ref(family), "entries": [{**history.describe(e, names), "actor": who.get(e.actor_id)} for e in rows],
            "next_after": next_after}


# ---------------------------------------------------------------- administration (Super Admins: their organisation)


def admin_registry(session: Session, admin: User, *, limit: int, offset: int, q: str | None = None,
                   workflow_status: str | None = None) -> tuple[list[dict], int]:
    conditions = [family_condition(admin)]
    if q:
        conditions.append(_matches_text(q))
    if workflow_status:
        conditions.append(CaseFamily.workflow_status == workflow_status)
    total = session.scalar(select(func.count()).select_from(CaseFamily).where(*conditions))
    families = list(session.scalars(select(CaseFamily).where(*conditions)
                                    .order_by(CaseFamily.created_at.desc(), CaseFamily.id).limit(limit).offset(offset)))
    ids = [f.id for f in families]
    leads = defaultdict(list)
    for member in session.scalars(select(CaseMember).where(CaseMember.case_family_id.in_(ids), CaseMember.revoked_at.is_(None),
                                                           CaseMember.role == MemberRole.LEAD.value)):
        leads[member.case_family_id].append(member.user_id)
    stations = {s.id: s.code for s in session.scalars(select(PoliceStation).where(PoliceStation.organization_id == admin.organization_id))}
    who = people(session, [u for users in leads.values() for u in users] + [f.supervisor_id for f in families])
    references, activity = _references(session, ids), last_activity(session, ids)
    allowed = list(sensitivities_up_to(admin.clearance))
    evidence = dict(session.execute(select(EvidenceItem.case_family_id, func.count()).where(
        EvidenceItem.case_family_id.in_(ids), EvidenceItem.classification.in_(allowed), EvidenceItem.status == FileStatus.ACTIVE.value)
        .group_by(EvidenceItem.case_family_id)).all())
    notes = dict(session.execute(select(Artifact.case_family_id, func.count()).where(
        Artifact.case_family_id.in_(ids), Artifact.status == FileStatus.ACTIVE.value).group_by(Artifact.case_family_id)).all())
    entries = dict(session.execute(select(CaseEntry.case_family_id, func.count()).where(CaseEntry.case_family_id.in_(ids))
                                   .group_by(CaseEntry.case_family_id)).all())
    items = []
    for f in families:
        items.append({
            **summary(f, references.get(f.id, []), None, activity.get(f.id)), "station_code": stations.get(f.station_id, ""),
            "leads": [who[u] for u in leads[f.id] if u in who], "supervisor": who.get(f.supervisor_id),
            "evidence_count": evidence.get(f.id, 0), "files": evidence.get(f.id, 0) + notes.get(f.id, 0), "entries": entries.get(f.id, 0),
        })
    return items, total
