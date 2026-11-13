"""Notes, analyses and other artifacts as a whole: their version history, and sealing (docs/case-management/13).

- Versions: every version of a note, oldest first, to anyone who may see the note.
- Sealing hides a note or analysis (e.g. the transcription of a sealed recording) from everyone but the case's
  supervisor and administrators. Nothing is removed. Each seal and unseal is a case_status_events row
  (field "seal") with the reason, and an entry of the case's history.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.mfa import require_strong_auth
from app.casemgmt import engine, history
from app.casemgmt.access import case_condition, supervises
from app.casemgmt.enums import FileStatus, HistoryKind, StatusField
from app.casemgmt.errors import Forbidden, Invalid, NotVisible
from app.casemgmt.models import Artifact, ArtifactVersion, CaseFamily, CaseStatusEvent
from app.db.models import User


def get_artifact(session: Session, user: User, artifact_id) -> tuple[Artifact, CaseFamily, list[ArtifactVersion]]:
    """An artifact the user may see, with its versions (oldest first); NotVisible (404) otherwise."""
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise NotVisible()
    family = session.scalar(select(CaseFamily).where(CaseFamily.id == artifact.case_family_id, case_condition(user)))
    if family is None or ((artifact.sealed or artifact.status == FileStatus.WITHDRAWN.value) and not supervises(user, family)):
        raise NotVisible(exists=True)
    versions = list(session.scalars(select(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact.id)
                                    .order_by(ArtifactVersion.version_number)))
    return artifact, family, versions


def set_sealed(session: Session, actor: User, artifact: Artifact, family: CaseFamily, *, sealed: bool, reason: str) -> None:
    family = engine._lock_family(session, family.id, artifact)
    if not supervises(actor, family):
        raise Forbidden("Only the case's supervisor or an administrator can seal or unseal notes and analyses")
    require_strong_auth(actor, "sealing or unsealing")
    if artifact.sealed == sealed:
        raise Invalid(f"{artifact.display_id} is already {'sealed' if sealed else 'not sealed'}")
    reason = engine._reason(reason)
    artifact.sealed = sealed
    artifact.sealed_reason, artifact.sealed_by, artifact.sealed_at = (reason, actor.id, dt.datetime.now(dt.UTC)) if sealed else (None, None, None)
    session.add(CaseStatusEvent(case_family_id=family.id, field=StatusField.SEAL.value, old_value="unsealed" if sealed else "sealed",
                                new_value="sealed" if sealed else "unsealed", actor_id=actor.id,
                                reason=f"{artifact.display_id}: {reason}"))
    session.flush()
    history.append(session, family, actor, HistoryKind.FILE_SEALED if sealed else HistoryKind.FILE_UNSEALED,
                   f"{artifact.display_id} {'sealed' if sealed else 'unsealed'}: {reason}", subject_type="artifact", subject_id=artifact.id,
                   details={"display_id": artifact.display_id, "reason": reason})
