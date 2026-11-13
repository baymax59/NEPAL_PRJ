"""Live notices and live pages (spec §3: "WebSocket or Server-Sent Events for real-time notifications").

A Server-Sent Events stream tells the browser two things, and never any case content:

- **notices**: the number of unread notices and the newest notice's number. The browser then fetches the notices
  through the normal, audited endpoint.
- **activity** (CM-8): when the browser says which page is open (`watch=case:<id>`, `evidence:<id>` or `admin`), a short
  fingerprint of everything that page shows and that can change: the case's history (every note, upload, import and report),
  statuses, the team, tasks, comments, custody, integrity checks, seals, report checks, legal holds and retention
  decisions. When the fingerprint changes, the browser fetches the page's data again, so a page stays current
  while colleagues work, without reloading.

Why a fingerprint and not a refresh every few seconds: every read of case data is audited permanently, so pages
re-read only when something really changed. Reads themselves never change the fingerprint (previews and downloads
are recorded as `accessed` custody events and preview/download/indexing integrity checks, which are left out), so a
refresh can't cause another one.

The scope is limited by the same rules as the pages (access.case_condition), checked again at every poll:
a page the user may not open gives no fingerprint at all, exactly like one that doesn't exist.

- No database connection is held while waiting: each check opens a short session.
- The stream ends when the login expires or the account is disabled (event `expired`), and after
  STREAM_SECONDS (event `reconnect`); the browser then connects again.
"""

import asyncio
import hashlib
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import bindparam, func, select, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.casemgmt import access
from app.casemgmt.models import CaseFamily, EvidenceItem, Notification
from app.db.models import User

POLL_SECONDS = 5.0
HEARTBEAT_SECONDS = 25.0  # a comment line now and then keeps proxies from closing a quiet connection
STREAM_SECONDS = 600.0
ADMIN_ACTIVITY_SECONDS = 15.0  # admin pages show the whole organisation: refreshed at most this often

WATCH_KINDS = ("case", "evidence")
WATCH_PATTERN = r"^(?:(?:case|evidence):[0-9a-fA-F-]{36}|admin)$"


def notice_state(session: Session, user_id) -> dict:
    unread = session.scalar(select(func.count()).select_from(Notification)
                            .where(Notification.user_id == user_id, Notification.read_at.is_(None)))
    latest = session.scalar(select(func.max(Notification.id)).where(Notification.user_id == user_id))
    return {"unread": unread or 0, "latest": latest}


# ---------------------------------------------------------------- live pages (CM-8)


@dataclass(frozen=True)
class Watch:
    """The page the browser has open."""

    kind: str  # case, evidence or admin
    id: uuid.UUID | None = None

    @property
    def label(self) -> str:
        return self.kind if self.id is None else f"{self.kind}:{self.id}"


def parse_watch(value: str | None) -> Watch | None:
    """`case:<uuid>`, `evidence:<uuid>` or `admin`; anything else: None."""
    if not value:
        return None
    if value == "admin":
        return Watch("admin")
    kind, _, raw = value.partition(":")
    if kind not in WATCH_KINDS:
        return None
    try:
        return Watch(kind, uuid.UUID(raw))
    except ValueError:
        return None


def watched_scope(session: Session, user: User, watch: Watch) -> list[uuid.UUID] | None:
    """The cases the watched page shows, limited to what the user may open; None for nothing."""
    if watch.kind == "admin":
        if not access.is_super_admin(user):
            return None
        condition = access.case_condition(user)  # every case of the organisation, within clearance
    elif watch.kind == "case":
        condition = CaseFamily.id == watch.id
    else:  # evidence: its case, if the user may see this exhibit (a sealed one stays hidden)
        item = session.get(EvidenceItem, watch.id)
        family = session.get(CaseFamily, item.case_family_id) if item is not None else None
        if family is None or not access.may_see_item(user, family, item):
            return None
        condition = CaseFamily.id == family.id
    rows = session.scalars(select(CaseFamily.id).where(condition, access.case_condition(user))).all()
    return sorted(rows) or None


_UUIDS = ARRAY(UUID(as_uuid=True))

# One row of values that change whenever something the watched page shows changes. Only changes made by people (or
# the daily checks) count: reads never change these values. Each subquery uses an index.
_MARKER = text("""
SELECT
  (SELECT max(e.id) FROM case_entries e WHERE e.case_family_id = ANY(:families)) AS entries,
  (SELECT md5(string_agg(f.workflow_status || '|' || coalesce(f.official_status, '') || '|' || coalesce(f.supervisor_id::text, ''),
                         ',' ORDER BY f.id)) FROM case_families f WHERE f.id = ANY(:families)) AS cases,
  (SELECT max(s.id) FROM case_status_events s WHERE s.case_family_id = ANY(:families)) AS statuses,
  (SELECT count(*) FROM case_official_references o WHERE o.case_family_id = ANY(:families)) AS official_references,
  (SELECT md5(string_agg(m.id::text || coalesce(m.revoked_at::text, ''), ',' ORDER BY m.id)) FROM case_members m
    WHERE m.case_family_id = ANY(:families)) AS members,
  (SELECT max(te.id) FROM task_events te JOIN investigation_tasks t ON t.id = te.task_id
    WHERE t.case_family_id = ANY(:families)) AS tasks,
  (SELECT count(*) FROM comments c WHERE c.case_family_id = ANY(:families)) AS comments,
  (SELECT max(c.id) FROM chain_of_custody_events c JOIN evidence_items it ON it.id = c.evidence_item_id
    WHERE it.case_family_id = ANY(:families) AND c.event_type <> 'accessed') AS custody,
  (SELECT max(k.id) FROM evidence_integrity_checks k JOIN evidence_items it ON it.id = k.evidence_item_id
    WHERE it.case_family_id = ANY(:families) AND k.trigger IN ('manual', 'scheduled', 'acknowledgement', 'upload')) AS integrity,
  (SELECT count(*) FILTER (WHERE a.sealed) FROM artifacts a WHERE a.case_family_id = ANY(:families)) AS sealed_artifacts,
  (SELECT max(rv.id) FROM report_verifications rv JOIN report_exports x ON x.id = rv.report_export_id
    WHERE x.case_family_id = ANY(:families)) AS report_checks,
  (SELECT md5(string_agg(h.id::text || coalesce(h.released_at::text, ''), ',' ORDER BY h.id)) FROM legal_holds h
    WHERE h.case_family_id = ANY(:families)) AS holds,
  (SELECT md5(string_agg(d.id::text || d.status, ',' ORDER BY d.id)) FROM retention_decisions d
    WHERE d.case_family_id = ANY(:families)) AS retention
""").bindparams(bindparam("families", type_=_UUIDS))

# What the admin pages show beyond the cases themselves.
_ADMIN_MARKER = text("""
SELECT
  (SELECT max(id) FROM job_runs) AS jobs,
  (SELECT max(id) FROM audit_checkpoints) AS checkpoints,
  (SELECT max(e.id) FROM integration_source_events e JOIN integration_sources s ON s.id = e.source_id
    WHERE s.organization_id = :org) AS sources,
  (SELECT md5(string_agg(p.id::text || p.status, ',' ORDER BY p.id)) FROM retention_policies p
    WHERE p.organization_id = :org) AS policies
""")


def activity_marker(session: Session, user: User, watch: Watch) -> str | None:
    """A short fingerprint of what the watched page shows; None if the user may not open it (or it doesn't exist)."""
    families = watched_scope(session, user, watch)
    if families is None:
        return None
    values: tuple = (tuple(str(f) for f in families), *session.execute(_MARKER, {"families": families}).one())
    if watch.kind == "admin":
        values += tuple(session.execute(_ADMIN_MARKER, {"org": user.organization_id}).one())
    return hashlib.sha256(repr(values).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- the stream


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


async def events(state: Callable[[], dict | None], disconnected: Callable[[], Awaitable[bool]], *,
                 scope: str | None = None, activity_every: float = 0.0) -> AsyncIterator[str]:
    """The stream. `state()` gives {"unread", "latest"} (plus "activity" when a page is watched), or None once the
    login is no longer valid. `activity_every`: the least time between two `activity` events."""
    yield "retry: 5000\n\n"  # how long the browser waits before reconnecting
    started, quiet = time.monotonic(), 0.0
    last_notices: dict | None = None
    last_activity: str | None = None
    activity_sent_at: float | None = None
    while True:
        current = await run_in_threadpool(state)
        if current is None:
            yield _event("expired", {})
            return
        sent = False
        notices = {"unread": current["unread"], "latest": current["latest"]}
        if notices != last_notices:
            yield _event("notices", notices)
            last_notices, sent = notices, True
        marker = current.get("activity")
        if marker is not None and marker != last_activity:
            now = time.monotonic()
            if activity_sent_at is None or now - activity_sent_at >= activity_every:
                yield _event("activity", {"scope": scope, "marker": marker})
                last_activity, activity_sent_at, sent = marker, now, True
        if sent:
            quiet = 0.0
        elif quiet >= HEARTBEAT_SECONDS:
            yield ": still here\n\n"
            quiet = 0.0
        if time.monotonic() - started >= STREAM_SECONDS:
            yield _event("reconnect", {})
            return
        await asyncio.sleep(POLL_SECONDS)
        quiet += POLL_SECONDS
        if await disconnected():
            return
