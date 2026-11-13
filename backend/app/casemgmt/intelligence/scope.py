"""What Case Intelligence may read in one case, for one user.

The rule of the whole phase: Case Intelligence never sees more than the user may see. The case's files are kept only if they are

- visible to the user (sealed exhibits and notes, and exhibits classified above the user's clearance, are left
  out exactly as on every other screen: access.hidden_file_ids), and
- active (a withdrawn file is history, not part of the case as it now stands).

Content that becomes part of the case record (the reconstructed timeline) is built from the *shared* view
instead: what every member of the case may see, whoever asks for it. So a supervisor rebuilding the timeline
can't copy a sealed exhibit's text into a note that investigators read.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.access import sensitivities_up_to
from app.casemgmt.access import hidden_file_ids
from app.casemgmt.enums import ArtifactType, FileStatus, TextSourceKind
from app.casemgmt.models import Artifact, ArtifactVersion, CaseFamily, CaseFolder, EvidenceItem, EvidenceVersion
from app.db.models import User


@dataclass(frozen=True)
class Source:
    """One file of a case that Case Intelligence may read, and the key of its text in the index."""

    path: str  # "folder/FILE-0001": where it is in the case
    kind: TextSourceKind
    item_id: uuid.UUID  # the exhibit or the artifact
    version_id: uuid.UUID
    display_id: str  # EV-0003, NOTE-0002, SUM-0001
    title: str
    version_number: int
    sha256: str  # the exhibit's bytes, or the artifact version's content
    mime_type: str | None = None
    category: str | None = None
    evidence_type: str | None = None
    size_bytes: int | None = None
    active_content: bool = False
    artifact_type: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind.value, self.sha256)

    def label(self, page_start: int | None = None, page_end: int | None = None) -> str:
        """How a passage of it is cited: 'EV-0002 v1, p.3', 'NOTE-0004 v2'."""
        where = ""
        if page_start is not None:
            where = f", p.{page_start}" if page_start == page_end or page_end is None else f", pp.{page_start}-{page_end}"
        return f"{self.display_id} v{self.version_number}{where}"


def shared_hidden_ids(session: Session, family: CaseFamily) -> set[uuid.UUID]:
    """Files that not every member of the case may see: sealed exhibits and notes, exhibits classified above the case."""
    allowed = sensitivities_up_to(family.classification)
    hidden = {item.id for item in session.scalars(select(EvidenceItem).where(EvidenceItem.case_family_id == family.id))
              if item.sealed or item.classification not in allowed}
    hidden |= set(session.scalars(select(Artifact.id).where(Artifact.case_family_id == family.id, Artifact.sealed.is_(True))))
    return hidden


def sources(session: Session, viewer: User | None, family: CaseFamily, *, shared: bool = False) -> list[Source]:
    """The case's active files that Case Intelligence may read: for `viewer`, or (shared=True) for everyone on the case.
    A note is read at its latest version."""
    if shared:
        hidden = shared_hidden_ids(session, family)
    elif viewer is not None:
        hidden = hidden_file_ids(session, viewer, family)
    else:
        raise ValueError("Say whose view: a viewer, or shared=True")
    folders = {f.id: f.name for f in session.scalars(select(CaseFolder).where(CaseFolder.case_family_id == family.id))}
    found: list[Source] = []
    for version, item in session.execute(
            select(EvidenceVersion, EvidenceItem).join(EvidenceItem, EvidenceVersion.evidence_item_id == EvidenceItem.id)
            .where(EvidenceItem.case_family_id == family.id, EvidenceItem.status == FileStatus.ACTIVE.value)):
        if item.id in hidden:
            continue
        found.append(Source(path=f"{folders[item.folder_id]}/{item.display_id}", kind=TextSourceKind.EVIDENCE, item_id=item.id,
                            version_id=version.id, display_id=item.display_id, title=item.title, version_number=version.version_number,
                            sha256=version.object_sha256, mime_type=version.mime_type, category=item.category,
                            evidence_type=item.evidence_type, size_bytes=version.size_bytes, active_content=version.active_content))
    latest: dict[uuid.UUID, tuple[ArtifactVersion, Artifact]] = {}
    for version, artifact in session.execute(
            select(ArtifactVersion, Artifact).join(Artifact, ArtifactVersion.artifact_id == Artifact.id)
            .where(Artifact.case_family_id == family.id, Artifact.status == FileStatus.ACTIVE.value)
            .order_by(ArtifactVersion.version_number)):
        if artifact.id not in hidden:
            latest[artifact.id] = (version, artifact)
    for version, artifact in latest.values():
        found.append(Source(path=f"{folders[artifact.folder_id]}/{artifact.display_id}", kind=TextSourceKind.ARTIFACT,
                            item_id=artifact.id, version_id=version.id, display_id=artifact.display_id, title=artifact.title,
                            version_number=version.version_number, sha256=version.content_sha256, artifact_type=artifact.artifact_type))
    return sorted(found, key=lambda source: source.path)


def source_view(source: Source) -> dict:
    """A source as the API shows it."""
    return {"path": source.path, "kind": source.kind.value, "item_id": source.item_id, "version_id": source.version_id,
            "display_id": source.display_id, "title": source.title, "version_number": source.version_number,
            "mime_type": source.mime_type, "evidence_type": source.evidence_type, "artifact_type": source.artifact_type}


# Generated content isn't read back into what generates it (a timeline built from an earlier timeline would only echo it).
GENERATED_TYPES = {ArtifactType.TIMELINE.value, ArtifactType.REPORT.value}
