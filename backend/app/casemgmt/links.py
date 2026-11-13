"""Case links (spec §21 screen 18, "Case links and relationship graph"; docs/case-management/05: case_links, 13).

"This case is related to that one, because ...". A link is case content like a note: a file of type `link` in the case's
"links" folder, with its own entry in the case's history (`link_added`). Removing a link is an ordinary withdrawal of the file
(it stays in the history). Links can't be edited: withdraw and link again.

`case_links` indexes every link, so a case also shows which cases link to it, but only cases the viewer can open. Linking needs
access to both cases.

A link can also point at a past case of the knowledge base (found by Similar Cases): the user must be allowed to see that case
(clearance and grants, as everywhere in Case Intelligence).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import AccessContext
from app.casemgmt import engine, history, queries
from app.casemgmt.access import case_condition, get_family, require, rights
from app.casemgmt.enums import ArtifactType, FileStatus, HistoryKind, LinkType
from app.casemgmt.errors import Conflict, Invalid, NotVisible
from app.casemgmt.models import Artifact, ArtifactVersion, CaseFamily, CaseLink
from app.db.models import Case, User

LINK_TYPES = {
    LinkType.RELATED: "Related case",
    LinkType.SAME_PERSON: "Same person of interest",
    LinkType.SAME_VICTIM: "Same victim or complainant",
    LinkType.SAME_METHOD: "Same method (modus operandi)",
    LinkType.SHARED_EVIDENCE: "Shared evidence or indicator",
    LinkType.SAME_PLACE: "Same place",
    LinkType.POSSIBLE_DUPLICATE: "Possible duplicate report",
    LinkType.PART_OF: "Part of a larger case",
}
FOLDER = "links"


def link_types() -> list[dict]:
    return [{"code": kind.value, "label": label} for kind, label in LINK_TYPES.items()]


def label(code: str) -> str:
    try:
        return LINK_TYPES[LinkType(code)]
    except ValueError:
        return code.replace("_", " ")


def knowledge_ref(case: Case) -> dict:
    return {"case_id": str(case.id), "display_id": case.display_id, "title": case.title, "court": case.court_or_agency,
            "decision_date": case.primary_date.isoformat() if case.primary_date else None, "source_system": case.source_system}


def add_link(session: Session, actor: User, family: CaseFamily, *, link_type: str, reason: str, target_case_id=None,
             knowledge_case: str | None = None, access: AccessContext | None = None) -> tuple[Artifact, CaseLink]:
    """Link another investigation (target_case_id) or a past case of the knowledge base (knowledge_case, its display ID)."""
    try:
        kind = LinkType(link_type)
    except ValueError:
        raise Invalid(f"Unknown kind of link: use one of {', '.join(k.value for k in LinkType)}") from None
    reason = (reason or "").strip()
    if not 10 <= len(reason) <= 1000:
        raise Invalid("Say why the cases are linked (10 to 1,000 characters): the reason stays with the link")
    if (target_case_id is None) == (knowledge_case is None):
        raise Invalid("Link either another investigation (target_case_id) or a past case (knowledge_case), not both")
    target = past = None
    if target_case_id is not None:
        target = get_family(session, actor, target_case_id)  # 404 for a case the user can't open
    else:
        if access is None:
            raise NotVisible()
        past = session.scalar(select(Case).where(Case.display_id == knowledge_case, access.case_condition()))
        if past is None:  # 404 whether it doesn't exist or the user may not see it
            raise NotVisible(exists=session.scalar(select(Case.id).where(Case.display_id == knowledge_case)) is not None)
    family = engine._lock_family(session, family.id)
    found = rights(session, actor, family)
    require(found.add_files, "You can read this case but not add to it", found)
    if target is not None and target.id == family.id:
        raise Invalid("A case can't be linked to itself")
    shown = target.display_id if target else past.display_id
    same_target = CaseLink.target_family_id == target.id if target else CaseLink.knowledge_case_id == past.id
    already = session.scalar(
        select(CaseLink.id).join(Artifact, Artifact.id == CaseLink.artifact_id)
        .where(CaseLink.case_family_id == family.id, Artifact.status == FileStatus.ACTIVE.value, same_target))
    if already is not None:
        raise Conflict(f"This case already links to {shown}. To change the link, withdraw it and link again.")

    if target is not None:
        content = {"target": {"case_id": str(target.id), "display_id": target.display_id, "title": target.title,
                              "case_type": target.case_type},
                   "link_type": kind.value, "reason": reason}
        title = f"{LINK_TYPES[kind]}: {target.display_id}"
    else:
        content = {"knowledge_case": knowledge_ref(past), "link_type": kind.value, "reason": reason}
        title = f"{LINK_TYPES[kind]}: {past.display_id} (past case)"
    folder = engine.ensure_folder(session, family, actor, FOLDER, system=True)
    artifact, version = engine._new_version(session, family=family, folder=folder, artifact=None, artifact_type=ArtifactType.LINK,
                                            title=title[:300], content=content, author=actor)
    link = CaseLink(organization_id=family.organization_id, case_family_id=family.id, artifact_id=artifact.id,
                    target_family_id=target.id if target else None, knowledge_case_id=past.id if past else None,
                    link_type=kind.value, reason=reason, created_by=actor.id)
    session.add(link)
    session.flush()
    history.append(session, family, actor, HistoryKind.LINK_ADDED,
                   f"{artifact.display_id} link to {shown}{'' if target else ' (past case)'}: {LINK_TYPES[kind].lower()}",
                   subject_type="artifact", subject_id=artifact.id,
                   details={"display_id": artifact.display_id, "target": shown, "link_type": kind.value, "knowledge_base": target is None,
                            "content_sha256": version.content_sha256})
    return artifact, link


def _openable(session: Session, viewer: User, family_ids) -> dict[uuid.UUID, CaseFamily]:
    """The cases among these that the viewer can open."""
    ids = {i for i in family_ids if i}
    if not ids:
        return {}
    return {f.id: f for f in session.scalars(select(CaseFamily).where(CaseFamily.id.in_(ids), case_condition(viewer)))}


def links_of(session: Session, viewer: User, family: CaseFamily, access: AccessContext | None = None) -> dict:
    """The links of the case (also withdrawn ones, marked so), and the links to the case from cases the viewer can open."""
    rows = list(session.execute(
        select(CaseLink, Artifact).join(Artifact, Artifact.id == CaseLink.artifact_id)
        .where(CaseLink.case_family_id == family.id).order_by(CaseLink.created_at, Artifact.display_id)).all())
    versions = {v.artifact_id: v for v in session.scalars(select(ArtifactVersion).where(
        ArtifactVersion.artifact_id.in_([a.id for _, a in rows])))} if rows else {}
    openable = _openable(session, viewer, [link.target_family_id for link, _ in rows])
    past_ids = {(versions[a.id].content or {}).get("knowledge_case", {}).get("display_id") for _, a in rows
                if (versions[a.id].content or {}).get("knowledge_case")}
    past_visible = set(session.scalars(select(Case.display_id).where(Case.display_id.in_(past_ids), access.case_condition()))) \
        if past_ids and access is not None else set()
    incoming_rows = list(session.execute(
        select(CaseLink, CaseFamily, Artifact).join(CaseFamily, CaseFamily.id == CaseLink.case_family_id)
        .join(Artifact, Artifact.id == CaseLink.artifact_id)
        .where(CaseLink.target_family_id == family.id, Artifact.status == FileStatus.ACTIVE.value, case_condition(viewer))
        .order_by(CaseLink.created_at.desc())).all())
    who = queries.people(session, [link.created_by for link, _ in rows] + [link.created_by for link, _, _ in incoming_rows])

    outgoing = []
    for link, artifact in rows:
        content = versions[artifact.id].content or {}
        outgoing.append({
            "link_id": link.id, "artifact_id": artifact.id, "display_id": artifact.display_id, "status": artifact.status,
            "withdrawn_reason": artifact.withdrawn_reason, "link_type": link.link_type, "label": label(link.link_type),
            "reason": link.reason, "target": content.get("target") or {},
            "target_now": queries.case_ref(openable[link.target_family_id]) if link.target_family_id in openable else None,
            "knowledge_case": content.get("knowledge_case"),
            "knowledge_visible": (content.get("knowledge_case") or {}).get("display_id") in past_visible,
            "created_by": who.get(link.created_by), "created_at": link.created_at,
        })
    incoming = [{"case": queries.case_ref(source), "link_type": link.link_type, "label": label(link.link_type), "reason": link.reason,
                 "created_by": who.get(link.created_by), "created_at": link.created_at} for link, source, _ in incoming_rows]
    return {"case": queries.case_ref(family), "outgoing": outgoing, "incoming": incoming, "link_types": link_types()}
