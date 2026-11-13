"""Content hashes for the history of a case (docs/case-management/13-plain-case-design.md §2).

Everything is hashed from canonical JSON (sorted keys, no spaces, UTF-8), so anyone can recompute an
entry's fingerprint from the stored fields and check that nothing was changed.
"""

import datetime as dt
import hashlib
import json
import uuid
from typing import Any


def _json_default(value: Any) -> str:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.UTC).isoformat()  # one representation, whatever the database's timezone
    if isinstance(value, dt.date):
        return value.isoformat()
    raise TypeError(f"Cannot hash a {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash(value: Any) -> str:
    return sha256_hex(canonical_json(value))


def entry_hash(
    *,
    case_family_id: uuid.UUID,
    seq: int,
    kind: str,
    actor_id: uuid.UUID,
    at: dt.datetime,
    subject_type: str | None,
    subject_id: str | None,
    summary: str,
    details: dict[str, Any],
    prev_hash: str | None,
) -> str:
    """The fingerprint of one history entry: everything it records, and the fingerprint of the entry before it.

    Changing, removing or reordering any entry of a case therefore changes every fingerprint after it (history.verify_chain)."""
    return content_hash(
        {
            "case_family_id": case_family_id,
            "seq": seq,
            "kind": kind,
            "actor_id": actor_id,
            "at": at,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "summary": summary,
            "details": details,
            "prev_hash": prev_hash,
        }
    )
