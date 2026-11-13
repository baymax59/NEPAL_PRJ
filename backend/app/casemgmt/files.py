"""The files of a case, folder by folder (docs/case-management/13-plain-case-design.md): exhibits and notes in one list.

Files the user may not see (sealed, or evidence above their clearance) are left out as if they weren't there.
A withdrawn file has left the team's view; whoever oversees the case (Supervisor, Administrator, Super Admin) still sees it, marked as
withdrawn, with who withdrew it, when and why.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.casemgmt import evidence_views, queries
from app.casemgmt.access import hidden_file_ids, supervises
from app.casemgmt.enums import FileStatus
from app.casemgmt.errors import Invalid
from app.casemgmt.models import Artifact, ArtifactVersion, CaseFamily, CaseFolder, EvidenceItem, EvidenceVersion
from app.db.models import User


def _note_row(artifact: Artifact, folder: CaseFolder, latest: ArtifactVersion, first: ArtifactVersion, who: dict) -> dict:
    return {"kind": "note", "id": artifact.id, "display_id": artifact.display_id, "title": artifact.title, "folder": folder.name,
            "status": artifact.status, "sealed": artifact.sealed, "type": artifact.artifact_type,
            "created_by": who.get(artifact.created_by), "created_at": artifact.created_at, "updated_at": latest.created_at,
            "version_number": latest.version_number, "withdrawn_reason": artifact.withdrawn_reason,
            "withdrawn_at": artifact.withdrawn_at, "withdrawn_by": who.get(artifact.withdrawn_by), "evidence": None}


def files(session: Session, user: User, family: CaseFamily, *, folder: str | None = None, include_withdrawn: bool = False) -> list[dict]:
    """Every file of the case the user may see (in one folder, when named), oldest first within each folder."""
    from app.casemgmt import engine

    hidden = hidden_file_ids(session, user, family)
    oversees = supervises(user, family)
    where = None
    if folder:
        where = engine.find_folder(session, family, folder)
        if where is None:
            raise Invalid(f"This case has no folder named '{folder[:60]}'")
    folders = {f.id: f for f in session.scalars(select(CaseFolder).where(CaseFolder.case_family_id == family.id)
                                                .order_by(CaseFolder.added_at, CaseFolder.name))}
    position = {f.name: i for i, f in enumerate(folders.values())}

    artifact_query = select(Artifact).where(Artifact.case_family_id == family.id)
    evidence_query = select(EvidenceItem, EvidenceVersion).join(EvidenceVersion, EvidenceVersion.evidence_item_id == EvidenceItem.id).where(
        EvidenceItem.case_family_id == family.id)
    if where is not None:
        artifact_query = artifact_query.where(Artifact.folder_id == where.id)
        evidence_query = evidence_query.where(EvidenceItem.folder_id == where.id)
    if not (include_withdrawn or oversees):
        artifact_query = artifact_query.where(Artifact.status == FileStatus.ACTIVE.value)
        evidence_query = evidence_query.where(EvidenceItem.status == FileStatus.ACTIVE.value)
    artifacts = [a for a in session.scalars(artifact_query.order_by(Artifact.created_at, Artifact.display_id)) if a.id not in hidden]
    pairs = [(i, v) for i, v in session.execute(evidence_query.order_by(EvidenceItem.created_at, EvidenceItem.display_id)).all()
             if i.id not in hidden]

    versions = {}
    if artifacts:
        for v in session.scalars(select(ArtifactVersion).where(ArtifactVersion.artifact_id.in_([a.id for a in artifacts]))
                                 .order_by(ArtifactVersion.version_number)):
            versions.setdefault(v.artifact_id, []).append(v)
    who = queries.people(session, [a.created_by for a in artifacts] + [i.created_by for i, _ in pairs]
                         + [a.withdrawn_by for a in artifacts] + [i.withdrawn_by for i, _ in pairs])
    described = evidence_views.summaries(session, pairs) if pairs else {}

    rows = []
    for a in artifacts:
        chain = versions[a.id]
        rows.append(_note_row(a, folders[a.folder_id], chain[-1], chain[0], who))
    for item, version in pairs:
        rows.append({"kind": "evidence", "id": item.id, "display_id": item.display_id, "title": item.title,
                     "folder": folders[item.folder_id].name, "status": item.status, "sealed": item.sealed, "type": item.evidence_type,
                     "created_by": who.get(item.created_by), "created_at": item.created_at, "updated_at": version.uploaded_at,
                     "version_number": None, "withdrawn_reason": item.withdrawn_reason, "withdrawn_at": item.withdrawn_at,
                     "withdrawn_by": who.get(item.withdrawn_by), "evidence": described[item.id]})
    rows.sort(key=lambda r: (position[r["folder"]], r["created_at"], r["display_id"]))
    return rows


def count_files(session: Session, family: CaseFamily) -> int:
    notes = session.scalar(select(func.count()).select_from(Artifact).where(Artifact.case_family_id == family.id,
                                                                            Artifact.status == FileStatus.ACTIVE.value))
    exhibits = session.scalar(select(func.count()).select_from(EvidenceItem).where(EvidenceItem.case_family_id == family.id,
                                                                                   EvidenceItem.status == FileStatus.ACTIVE.value))
    return (notes or 0) + (exhibits or 0)


def view(session: Session, user: User, family: CaseFamily, *, folder: str | None, include_withdrawn: bool) -> dict:
    return {"case": queries.case_ref(family), "folders": queries.folders_of(session, user, family),
            "files": files(session, user, family, folder=folder, include_withdrawn=include_withdrawn)}

