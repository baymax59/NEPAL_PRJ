"""The hash-chained audit trail and its signed checkpoints (phase CM-7, docs/case-management/04 §8).

The database chains every Case Management event (action "cm.*") as it is written (trigger cm_audit_events_chain,
migration 0014):

    hash = sha256(previous hash | sequence | id | time | user | action | outcome | target | address | details)

So an edited event no longer matches its hash, a removed one leaves a gap in the sequence, and a re-ordered or
inserted one breaks the link to the previous hash. Chained events can't be changed or deleted (a database rule).

Someone with full control of the database could still recompute every hash after an edit. Checkpoints stop that:
the latest (sequence, hash) is signed with an HMAC key kept OUTSIDE the database (setting CM_CHECKPOINT_KEY) and
also written as a file to the write-once evidence store. A recomputed chain no longer matches the signed checkpoints.
This is detection, not prevention: see docs/case-management/07 §2.
"""

import datetime as dt
import hashlib
import hmac
import io
import json
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.casemgmt import hashing
from app.casemgmt.enums import CheckpointReason
from app.casemgmt.errors import Invalid
from app.casemgmt.models import AuditCheckpoint
from app.casemgmt.storage import EvidenceStore
from app.core.config import get_settings
from app.db.models import AuditEvent, User

ZERO = "0" * 64
BATCH = 5000
MAX_LISTED_BREAKS = 25


@dataclass
class ChainBreak:
    chain_seq: int
    problem: str  # edited, missing, out_of_order, checkpoint_mismatch, bad_signature, other_key, checkpoint_file
    detail: str
    event_id: int | None = None


@dataclass
class ChainReport:
    events: int = 0
    last_seq: int | None = None
    last_hash: str | None = None
    checkpoints: int = 0
    checkpoints_verified: int = 0
    since_last_checkpoint: int = 0
    breaks: list[ChainBreak] = field(default_factory=list)
    more_breaks: int = 0
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None

    @property
    def intact(self) -> bool:
        return not self.breaks

    def add(self, problem: ChainBreak) -> None:
        if len(self.breaks) < MAX_LISTED_BREAKS:
            self.breaks.append(problem)
        else:
            self.more_breaks += 1

    def as_dict(self) -> dict:
        return {"intact": self.intact, "events": self.events, "last_seq": self.last_seq, "last_hash": self.last_hash,
                "checkpoints": self.checkpoints, "checkpoints_verified": self.checkpoints_verified,
                "since_last_checkpoint": self.since_last_checkpoint, "more_breaks": self.more_breaks,
                "breaks": [b.__dict__ for b in self.breaks], "started_at": self.started_at, "finished_at": self.finished_at}


def checkpoint_key() -> bytes:
    """The signing key: CM_CHECKPOINT_KEY, or (until one is set) a key derived from AUDIT_SECRET, for its own purpose."""
    settings = get_settings()
    if settings.cm_checkpoint_key is not None:
        return settings.cm_checkpoint_key.get_secret_value().encode()
    return hmac.new(settings.audit_secret.get_secret_value().encode(), b"case-management audit checkpoint v1", hashlib.sha256).digest()


def key_id(key: bytes) -> str:
    """Which key signed a checkpoint, without revealing it."""
    return hashlib.sha256(b"knight-hawk checkpoint key id|" + key).hexdigest()[:12]


def _signed(chain_seq: int, chain_hash: str, created_at: dt.datetime) -> bytes:
    return f"knight-hawk-audit-checkpoint|v1|{chain_seq}|{chain_hash}|{created_at.isoformat()}".encode()


def sign(key: bytes, chain_seq: int, chain_hash: str, created_at: dt.datetime) -> str:
    return hmac.new(key, _signed(chain_seq, chain_hash, created_at), hashlib.sha256).hexdigest()


def latest(session: Session) -> tuple[int, str] | None:
    row = session.execute(select(AuditEvent.chain_seq, AuditEvent.hash).where(AuditEvent.chain_seq.is_not(None))
                          .order_by(AuditEvent.chain_seq.desc()).limit(1)).first()
    return (row.chain_seq, row.hash) if row else None


def create_checkpoint(session: Session, store: EvidenceStore, actor: User | None, reason: CheckpointReason) -> AuditCheckpoint:
    """Sign the chain as it stands now, and keep the signed record in the write-once store too."""
    last = latest(session)
    if last is None:
        raise Invalid("Nothing to sign yet: no Case Management event has been recorded")
    chain_seq, chain_hash = last
    if session.scalar(select(AuditCheckpoint.id).where(AuditCheckpoint.chain_seq == chain_seq)):
        raise Invalid(f"The chain is already signed up to event {chain_seq}: nothing new to sign")
    created = dt.datetime.now(dt.UTC)
    key = checkpoint_key()
    signature = sign(key, chain_seq, chain_hash, created)
    document = {"knight_hawk_audit_checkpoint": 1, "chain_seq": chain_seq, "chain_hash": chain_hash,
                "created_at": created.isoformat(), "key_id": key_id(key), "signature": signature,
                "database": get_settings().postgres_db}
    incoming = store.receive(io.BytesIO(hashing.canonical_json(document)), max_bytes=1_000_000)
    storage_key, _ = store.keep(incoming)
    checkpoint = AuditCheckpoint(chain_seq=chain_seq, chain_hash=chain_hash, signature=signature, key_id=key_id(key),
                                 reason=reason.value, stored_sha256=incoming.sha256, storage_key=storage_key,
                                 created_by=actor.id if actor else None, created_at=created)
    session.add(checkpoint)
    session.flush()
    return checkpoint


_ROWS = text("""
    SELECT chain_seq, id, prev_hash, hash, cm_audit_hash(prev_hash, audit_events) = hash AS intact
    FROM audit_events WHERE chain_seq IS NOT NULL AND chain_seq > :after ORDER BY chain_seq LIMIT :n
""")


def verify(session: Session, store: EvidenceStore | None = None) -> ChainReport:
    """Recompute the whole chain, then check every checkpoint: its signature, its event, and its stored file."""
    report = ChainReport(started_at=dt.datetime.now(dt.UTC))
    checkpoints = list(session.scalars(select(AuditCheckpoint).order_by(AuditCheckpoint.chain_seq)))
    wanted = {c.chain_seq for c in checkpoints}
    hashes_at: dict[int, str] = {}
    expected, previous, after = 1, ZERO, 0
    while True:
        rows = session.execute(_ROWS, {"after": after, "n": BATCH}).all()
        if not rows:
            break
        for row in rows:
            if row.chain_seq != expected:
                report.add(ChainBreak(expected, "missing", f"events {expected} to {row.chain_seq - 1} are missing from the chain"))
            elif row.prev_hash != previous:
                report.add(ChainBreak(row.chain_seq, "out_of_order", "this event doesn't follow the one before it", row.id))
            if not row.intact:
                report.add(ChainBreak(row.chain_seq, "edited", "this event was changed after it was recorded", row.id))
            if row.chain_seq in wanted:
                hashes_at[row.chain_seq] = row.hash
            report.events += 1
            previous, expected, after = row.hash, row.chain_seq + 1, row.chain_seq
            report.last_seq, report.last_hash = row.chain_seq, row.hash

    key = checkpoint_key()
    current_key = key_id(key)
    report.checkpoints = len(checkpoints)
    for checkpoint in checkpoints:
        ok = True
        if checkpoint.key_id != current_key:
            report.add(ChainBreak(checkpoint.chain_seq, "other_key",
                                  f"signed with another key ({checkpoint.key_id}): can't be checked with the current key"))
            ok = False
        elif not hmac.compare_digest(sign(key, checkpoint.chain_seq, checkpoint.chain_hash, checkpoint.created_at), checkpoint.signature):
            report.add(ChainBreak(checkpoint.chain_seq, "bad_signature", "the checkpoint's signature is not valid: it was altered"))
            ok = False
        if hashes_at.get(checkpoint.chain_seq) != checkpoint.chain_hash:
            report.add(ChainBreak(checkpoint.chain_seq, "checkpoint_mismatch",
                                  "the chain no longer matches what was signed at this point: events before it were changed"))
            ok = False
        if store is not None and not _file_matches(store, checkpoint):
            report.add(ChainBreak(checkpoint.chain_seq, "checkpoint_file", "the checkpoint's file in the write-once store is missing or differs"))
            ok = False
        report.checkpoints_verified += ok
    if report.last_seq is not None:
        report.since_last_checkpoint = report.last_seq - (checkpoints[-1].chain_seq if checkpoints else 0)
    report.finished_at = dt.datetime.now(dt.UTC)
    return report


def _file_matches(store: EvidenceStore, checkpoint: AuditCheckpoint) -> bool:
    if store.hash(checkpoint.storage_key) != checkpoint.stored_sha256:
        return False
    try:
        stored = json.loads(b"".join(store.chunks(checkpoint.storage_key)))
    except (OSError, ValueError):
        return False
    return (stored.get("chain_seq") == checkpoint.chain_seq and stored.get("chain_hash") == checkpoint.chain_hash
            and stored.get("signature") == checkpoint.signature)


def checkpoint_view(checkpoint: AuditCheckpoint, who: dict) -> dict:
    return {"id": checkpoint.id, "chain_seq": checkpoint.chain_seq, "chain_hash": checkpoint.chain_hash, "key_id": checkpoint.key_id,
            "reason": checkpoint.reason, "stored_sha256": checkpoint.stored_sha256, "created_at": checkpoint.created_at,
            "created_by": who.get(checkpoint.created_by)}
