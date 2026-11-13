"""The history of a case: one chain of entries (docs/case-management/13-plain-case-design.md §2).

Everything that happens in a case adds an entry: folders and files added, a file withdrawn or sealed, people joining or leaving, status
changes, links, imports, reports. Each entry holds the fingerprint of the entry before it, so changing, removing or reordering any
entry is detected by `verify_chain`. The database also refuses an entry that is not exactly the next one (trigger
cm_case_entries_in_order) and any change or deletion of an entry.

Callers hold the case's lock (`engine._lock_family`), which makes the entries of a case take turns; each function runs inside the
caller's transaction.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.casemgmt import hashing
from app.casemgmt.enums import HistoryKind
from app.casemgmt.models import CaseEntry, CaseFamily
from app.db.models import User

MAX_SUMMARY = 500


def last_entry(session: Session, family_id) -> CaseEntry | None:
    return session.scalar(select(CaseEntry).where(CaseEntry.case_family_id == family_id).order_by(CaseEntry.seq.desc()).limit(1))


def _fingerprint(entry: CaseEntry) -> str:
    return hashing.entry_hash(case_family_id=entry.case_family_id, seq=entry.seq, kind=entry.kind, actor_id=entry.actor_id, at=entry.at,
                              subject_type=entry.subject_type, subject_id=entry.subject_id, summary=entry.summary,
                              details=entry.details, prev_hash=entry.prev_hash)


def append(session: Session, family: CaseFamily, actor: User, kind: HistoryKind, summary: str, *, subject_type: str | None = None,
           subject_id: Any = None, details: dict[str, Any] | None = None) -> CaseEntry:
    """Add the next entry of the case's history (the case must be locked by the caller)."""
    previous = last_entry(session, family.id)
    now = dt.datetime.now(dt.UTC)
    at = max(now, previous.at + dt.timedelta(microseconds=1)) if previous else now  # never earlier than the entry before it
    entry = CaseEntry(
        case_family_id=family.id, seq=previous.seq + 1 if previous else 1, kind=HistoryKind(kind).value, actor_id=actor.id, at=at,
        subject_type=subject_type, subject_id=str(subject_id) if subject_id is not None else None,
        summary=summary.strip()[:MAX_SUMMARY], details=details or {}, prev_hash=previous.entry_hash if previous else None,
        entry_hash="",
    )
    entry.entry_hash = _fingerprint(entry)
    session.add(entry)
    session.flush()
    return entry


def latest_entries(session: Session, family_id, count: int) -> list[CaseEntry]:
    """The newest `count` entries, oldest of them first (for a "recent activity" list)."""
    rows = list(session.scalars(select(CaseEntry).where(CaseEntry.case_family_id == family_id).order_by(CaseEntry.seq.desc()).limit(count)))
    return rows[::-1]


def entries(session: Session, family_id, *, limit: int = 50, after_seq: int | None = None) -> tuple[list[CaseEntry], int | None]:
    """The case's history, oldest first, a page at a time; the second value is where the next page starts (None at the end)."""
    query = select(CaseEntry).where(CaseEntry.case_family_id == family_id)
    if after_seq is not None:
        query = query.where(CaseEntry.seq > after_seq)
    rows = list(session.scalars(query.order_by(CaseEntry.seq).limit(limit + 1)))
    if len(rows) > limit:
        return rows[:limit], rows[limit - 1].seq
    return rows, None


def verify_chain(session: Session, family_id) -> dict:
    """Recompute every entry's fingerprint, and check each one names the one before it.

    {"entries": n, "intact": bool, "first_problem": seq or None, "problem": text or None}"""
    previous: CaseEntry | None = None
    count = 0
    for entry in session.scalars(select(CaseEntry).where(CaseEntry.case_family_id == family_id).order_by(CaseEntry.seq)):
        count += 1
        problem = None
        if entry.seq != (previous.seq + 1 if previous else 1):
            problem = "an entry is missing or out of order"
        elif entry.prev_hash != (previous.entry_hash if previous else None):
            problem = "the entry does not follow the one before it"
        elif entry.entry_hash != _fingerprint(entry):
            problem = "the entry was changed after it was written"
        if problem:
            return {"entries": count, "intact": False, "first_problem": entry.seq, "problem": problem}
        previous = entry
    return {"entries": count, "intact": True, "first_problem": None, "problem": None}


def describe(entry: CaseEntry, names: dict[uuid.UUID, str]) -> dict:
    """An entry as the screens show it."""
    return {"seq": entry.seq, "kind": entry.kind, "at": entry.at, "actor": names.get(entry.actor_id), "actor_id": entry.actor_id,
            "summary": entry.summary, "subject_type": entry.subject_type, "subject_id": entry.subject_id, "details": entry.details}
