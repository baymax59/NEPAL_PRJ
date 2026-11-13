"""Evidence: original exhibits, their bytes, integrity, sealing and download links (docs/case-management/04 §3, 13).

- An exhibit is added to a folder of the case by someone who may add files (the Investigator, a Sub Investigator, an Analyst, or the
  supervisor), and is at once part of the case and an entry of its history. Its bytes go to the write-once store under their
  SHA-256 (storage.py).
- An exhibit has exactly one version: the original. It never changes. Corrections, transcriptions and
  analyses are notes that name it in `derived_from`. A wrong exhibit is withdrawn with a reason (engine.withdraw_file), never deleted.
- Who sees an exhibit: someone who can open the case, with enough clearance; a sealed exhibit only the
  case's supervisor and administrators. Everyone else gets 404, exactly as for something missing.
- Callers check access first and write the audit events. Each function runs in the caller's transaction.
"""

import datetime as dt
import hashlib
import hmac
import re
import uuid
from dataclasses import dataclass

import jwt
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth.mfa import require_strong_auth
from app.auth.access import sensitivities_up_to
from app.casemgmt import engine, filetypes, history
from app.casemgmt.access import case_condition, hidden_file_ids, may_see_item, require, rights, supervises
from app.casemgmt.enums import (
    CustodyEventType,
    FileStatus,
    HistoryKind,
    IntegrityResult,
    IntegrityTrigger,
)
from app.casemgmt.errors import Forbidden, Invalid, NotVisible
from app.casemgmt.models import (
    Artifact,
    ArtifactVersion,
    CaseEntry,
    CaseFamily,
    CustodyEvent,
    EvidenceItem,
    EvidenceObject,
    EvidenceSourceReference,
    EvidenceVersion,
    IntegrityCheck,
)
from app.casemgmt.storage import EvidenceStore, Incoming
from app.core.config import get_settings
from app.db.models import User
from app.uploads.service import display_name

TYPE_CODE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
LINK_PURPOSE = "evidence-download"


@dataclass
class Seen:
    """An exhibit the user may see, with its original version, its bytes' record and its case."""

    item: EvidenceItem
    version: EvidenceVersion
    obj: EvidenceObject
    family: CaseFamily


@dataclass
class EvidenceMetadata:
    """What the person adding an exhibit tells about it (the upload form)."""

    title: str
    folder: str
    evidence_type: str | None = None
    description: str | None = None
    classification: str | None = None
    source: str | None = None
    collected_at: dt.datetime | None = None
    collected_by: str | None = None
    collection_authority: str | None = None
    source_system: str | None = None
    source_record_id: str | None = None
    source_hash: str | None = None


@dataclass
class Added:
    seen: Seen
    folder: str
    entry: CaseEntry
    duplicates: list[EvidenceItem]  # other exhibits of the case with exactly the same bytes


# ---------------------------------------------------------------- small helpers


def slug(filename: str | None) -> str:
    """A tidy file name for display: lower-case letters, digits, '.', '_' and '-'."""
    name = re.sub(r"[^a-z0-9._-]+", "-", display_name(filename).lower())
    name = re.sub(r"-{2,}", "-", name).strip("-._")
    return name[:200] or "file"


def _optional(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def tz_label(value: dt.datetime) -> str:
    minutes = int(value.utcoffset().total_seconds() // 60)
    sign, minutes = ("+" if minutes >= 0 else "-"), abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def moment(value: dt.datetime | None, what: str) -> tuple[dt.datetime | None, str | None]:
    """(the time in UTC, the timezone it was given in). A time without a timezone is ambiguous: refused."""
    if value is None:
        return None, None
    if value.tzinfo is None or value.utcoffset() is None:
        raise Invalid(f"{what} needs a timezone, e.g. 2026-11-02T14:30:00+05:30")
    if value > dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5):
        raise Invalid(f"{what} is in the future")
    return value.astimezone(dt.UTC), tz_label(value)


def custody_event(session: Session, seen: Seen, event_type: CustodyEventType, actor: User, *,
                  occurred_at: dt.datetime | None = None, occurred_tz: str | None = None, **fields) -> CustodyEvent:
    event = CustodyEvent(evidence_item_id=seen.item.id, evidence_version_id=seen.version.id, event_type=event_type.value,
                         actor_id=actor.id, occurred_at=occurred_at or dt.datetime.now(dt.UTC), occurred_tz=occurred_tz,
                         **fields)
    session.add(event)
    session.flush()
    return event


# ---------------------------------------------------------------- who can see an exhibit


def get_evidence(session: Session, user: User, evidence_id) -> Seen:
    """An exhibit the user may see, or NotVisible (404) whatever the reason."""
    item = session.get(EvidenceItem, evidence_id)
    if item is None:
        raise NotVisible()
    family = session.scalar(select(CaseFamily).where(CaseFamily.id == item.case_family_id, case_condition(user)))
    if family is None or not may_see_item(user, family, item):
        raise NotVisible(exists=True)
    version = session.scalar(select(EvidenceVersion).where(EvidenceVersion.evidence_item_id == item.id))
    return Seen(item, version, session.get(EvidenceObject, version.object_sha256), family)


def derived_versions(session: Session, user: User, seen: Seen) -> list[tuple[ArtifactVersion, Artifact]]:
    """Analyses, transcriptions and notes based on this exhibit, that the user can see."""
    hidden = hidden_file_ids(session, user, seen.family)
    candidates = session.execute(
        select(ArtifactVersion, Artifact).join(Artifact, ArtifactVersion.artifact_id == Artifact.id)
        .where(Artifact.case_family_id == seen.family.id, Artifact.status == FileStatus.ACTIVE.value,
               ArtifactVersion.derived_from.contains([str(seen.version.id)]))
        .order_by(ArtifactVersion.created_at, Artifact.display_id, ArtifactVersion.version_number)  # versions made at the same moment keep their order
    ).all()
    return [(v, a) for v, a in candidates if a.id not in hidden]


# ---------------------------------------------------------------- adding an exhibit


def _classification(meta: EvidenceMetadata, family: CaseFamily, actor: User) -> str:
    classification = meta.classification or family.classification
    if family.classification not in sensitivities_up_to(classification):
        raise Invalid(f"Evidence can't be classified lower than its case ({family.classification})")
    if classification not in sensitivities_up_to(actor.clearance):
        raise Invalid("You can't classify evidence above your own clearance")
    return classification


def add_evidence(session: Session, actor: User, family: CaseFamily, store: EvidenceStore, incoming: Incoming, *,
                 filename: str | None, declared_mime: str | None, meta: EvidenceMetadata) -> Added:
    """Store an uploaded exhibit in a folder of the case. A refused upload leaves nothing in the store."""
    try:
        family = engine._lock_family(session, family.id)
        found = rights(session, actor, family)
        require(found.add_files, "You can read this case but not add to it", found)
        title = (meta.title or "").strip()
        if not 3 <= len(title) <= 300:
            raise Invalid("A title of 3 to 300 characters is required")
        folder = engine.folder_named(session, family, meta.folder)
        classification = _classification(meta, family, actor)
        evidence_type = _optional(meta.evidence_type)
        if evidence_type and not TYPE_CODE.fullmatch(evidence_type):
            raise Invalid("The evidence type is a short code: lower-case letters, digits, '_' and '-'")
        collected_at, collected_tz = moment(meta.collected_at, "collected_at")
        found_type = filetypes.check(incoming.head, display_name(filename), accept_programs=get_settings().evidence_accept_programs)
    except BaseException:
        store.discard(incoming)
        raise
    key, _ = store.keep(incoming)

    session.execute(insert(EvidenceObject).values(sha256=incoming.sha256, size_bytes=incoming.size, mime_type=found_type.mime,
                                                  storage_backend=store.backend, storage_key=key)
                    .on_conflict_do_nothing(index_elements=["sha256"]))
    number = 1 + session.scalar(select(func.count()).select_from(EvidenceItem).where(EvidenceItem.case_family_id == family.id))
    item = EvidenceItem(
        case_family_id=family.id, folder_id=folder.id, display_id=f"EV-{number:04d}", title=title,
        evidence_type=evidence_type or found_type.category.value, category=found_type.category.value, classification=classification,
        description=_optional(meta.description), source=_optional(meta.source), collected_at=collected_at, collected_tz=collected_tz,
        collected_by=_optional(meta.collected_by), collection_authority=_optional(meta.collection_authority), created_by=actor.id,
        created_at=dt.datetime.now(dt.UTC),  # the real clock: files list in the order they were made
    )
    session.add(item)
    session.flush()
    version = EvidenceVersion(
        evidence_item_id=item.id, object_sha256=incoming.sha256, original_filename=display_name(filename),
        display_filename=slug(filename), mime_type=found_type.mime, declared_mime_type=(_optional(declared_mime) or "")[:100] or None,
        size_bytes=incoming.size, active_content=found_type.active, uploaded_by=actor.id,
    )
    session.add(version)
    session.flush()
    seen = Seen(item, version, session.get(EvidenceObject, incoming.sha256), family)
    if _optional(meta.source_system):
        session.add(EvidenceSourceReference(evidence_version_id=version.id, source_system=meta.source_system.strip(),
                                            source_record_id=_optional(meta.source_record_id),
                                            source_hash=_optional(meta.source_hash), imported_by=actor.id))
    if collected_at or item.collected_by or item.source or item.collection_authority:
        custody_event(session, seen, CustodyEventType.COLLECTED, actor, occurred_at=collected_at, occurred_tz=collected_tz,
                      from_custodian_name=item.source, to_custodian_name=item.collected_by,
                      authorization_ref=item.collection_authority, reason="Collection, as recorded when the exhibit was added",
                      details={"time_known": collected_at is not None})
    custody_event(session, seen, CustodyEventType.INGESTED, actor, to_custodian_id=actor.id, method="upload",
                  verification_sha256=incoming.sha256, details={"folder": folder.name, "size_bytes": incoming.size})
    entry = history.append(session, family, actor, HistoryKind.EVIDENCE_ADDED, f"{item.display_id} {title} added to {folder.name}",
                           subject_type="evidence", subject_id=item.id,
                           details={"display_id": item.display_id, "folder": folder.name, "sha256": incoming.sha256,
                                    "size_bytes": incoming.size})

    twins = session.scalars(select(EvidenceItem).join(EvidenceVersion, EvidenceVersion.evidence_item_id == EvidenceItem.id)
                            .where(EvidenceItem.case_family_id == family.id, EvidenceVersion.object_sha256 == incoming.sha256,
                                   EvidenceItem.id != item.id).order_by(EvidenceItem.display_id))
    duplicates = [twin for twin in twins if _can_see(session, actor, twin.id)]
    return Added(seen, folder.name, entry, duplicates)


def _can_see(session: Session, user: User, evidence_id) -> bool:
    try:
        get_evidence(session, user, evidence_id)
        return True
    except NotVisible:
        return False


# ---------------------------------------------------------------- integrity


def check_object(session: Session, store: EvidenceStore, obj: EvidenceObject, *, actor: User | None,
                 trigger: IntegrityTrigger, item_id=None) -> IntegrityCheck:
    """Recompute the stored file's SHA-256 and record the result (match, mismatch or missing)."""
    computed = store.hash(obj.storage_key)
    if computed is None:
        result = IntegrityResult.MISSING
    else:
        result = IntegrityResult.MATCH if hmac.compare_digest(computed, obj.sha256) else IntegrityResult.MISMATCH
    check = IntegrityCheck(object_sha256=obj.sha256, evidence_item_id=item_id, checked_by=actor.id if actor else None,
                           trigger=trigger.value, result=result.value, computed_sha256=computed)
    session.add(check)
    session.flush()
    return check


def verify(session: Session, actor: User, store: EvidenceStore, seen: Seen) -> IntegrityCheck:
    """An integrity check asked for by a person: recorded, and added to the chain of custody."""
    check = check_object(session, store, seen.obj, actor=actor, trigger=IntegrityTrigger.MANUAL, item_id=seen.item.id)
    custody_event(session, seen, CustodyEventType.VERIFIED, actor, verification_sha256=check.computed_sha256,
                  method="sha256", details={"result": check.result, "integrity_check": check.id})
    return check


def sweep(session: Session, store: EvidenceStore, actor: User | None) -> list[IntegrityCheck]:
    """Check every stored object (the periodic job, scripts/verify_evidence.py)."""
    return [check_object(session, store, obj, actor=actor, trigger=IntegrityTrigger.SCHEDULED)
            for obj in session.scalars(select(EvidenceObject).order_by(EvidenceObject.stored_at))]


# ---------------------------------------------------------------- sealing


def set_sealed(session: Session, actor: User, seen: Seen, *, sealed: bool, reason: str) -> None:
    """Seal (hide from everyone but the supervisor and administrators) or unseal. Nothing is removed."""
    family = engine._lock_family(session, seen.family.id, seen.item)
    if not supervises(actor, family):
        raise Forbidden("Only the case's supervisor or an administrator can seal or unseal evidence")
    require_strong_auth(actor, "sealing or unsealing evidence")
    if seen.item.sealed == sealed:
        raise Invalid(f"{seen.item.display_id} is already {'sealed' if sealed else 'not sealed'}")
    reason = engine._reason(reason)
    item = seen.item
    item.sealed = sealed
    item.sealed_reason, item.sealed_by, item.sealed_at = (reason, actor.id, dt.datetime.now(dt.UTC)) if sealed else (None, None, None)
    session.flush()
    custody_event(session, seen, CustodyEventType.SEALED if sealed else CustodyEventType.UNSEALED, actor, reason=reason)
    history.append(session, family, actor, HistoryKind.FILE_SEALED if sealed else HistoryKind.FILE_UNSEALED,
                   f"{item.display_id} {'sealed' if sealed else 'unsealed'}: {reason}", subject_type="evidence", subject_id=item.id,
                   details={"display_id": item.display_id, "reason": reason})


# ---------------------------------------------------------------- download links


def _token_key() -> bytes:
    """A key of its own, derived from the login secret: a download link can't be used to log in, nor the reverse."""
    secret = get_settings().jwt_secret.get_secret_value().encode()
    return hmac.new(secret, b"case-management evidence download v1", hashlib.sha256).digest()


def issue_download_token(user: User, seen: Seen) -> tuple[str, dt.datetime]:
    now = dt.datetime.now(dt.UTC)
    expires = now + dt.timedelta(minutes=get_settings().evidence_download_minutes)
    claims = {"sub": str(user.id), "evi": str(seen.item.id), "ver": str(seen.version.id), "iat": now, "exp": expires,
              "jti": uuid.uuid4().hex, "purpose": LINK_PURPOSE}
    return jwt.encode(claims, _token_key(), algorithm="HS256"), expires


def read_download_token(token: str) -> dict | None:
    """The claims of a valid, unexpired download link; None for anything else."""
    try:
        claims = jwt.decode(token, _token_key(), algorithms=["HS256"], options={"require": ["exp", "iat", "sub", "jti"]})
        for key in ("sub", "evi", "ver"):
            uuid.UUID(claims[key])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None
    return claims if claims.get("purpose") == LINK_PURPOSE else None
