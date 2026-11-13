"""Case Management API: what the screens need beyond the case itself (docs/case-management/13).

Police stations; choosing colleagues by name; the dashboards' figures; the live notification stream; case links; the report preview.
The same rules as the rest of the module: access inside the queries, 404 for anything not visible,
every request audited, nothing deleted. Included before the module's main router, whose catch-all answers 405
to deletions on these paths too.
"""

import uuid
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.access import AccessContext
from app.auth.dependencies import CurrentUser, get_access_context, oauth2_scheme
from app.auth.tokens import read_access_token
from app.casemgmt import colleagues, links, overview, report, stations, stream
from app.casemgmt import schemas as s
from app.casemgmt.access import get_family
from app.casemgmt.api import Audit, Audited, DbSession, IdempotencyKeyHeader, _require_admin
from app.casemgmt.idempotency import Once
from app.db.models import User
from app.db.session import get_session_factory

router = APIRouter(prefix="/v1", tags=["case management: workspace"])
Access = Annotated[AccessContext, Depends(get_access_context)]


# ---------------------------------------------------------------- police stations


@router.get("/stations", response_model=list[s.StationOut])
def my_stations(user: CurrentUser, db: DbSession, audit: Audit) -> list[dict]:
    """The police stations the user may register cases at: every station for a Super Admin, else their own."""
    with Audited(db, audit, user, "cm.stations.list", "cm_case") as event:
        result = [{"id": st.id, "code": st.code, "name": st.name, "district": st.district, "status": st.status}
                  for st in stations.usable_stations(db, user)]
        event.read(count=len(result))
    return result


# ---------------------------------------------------------------- choosing colleagues


@router.get("/colleagues", response_model=list[s.Colleague])
def find_colleagues(user: CurrentUser, db: DbSession, audit: Audit, purpose: Literal["lead", "supervisor", "team"],
                    classification: Annotated[str | None, Query(max_length=16)] = None, case_id: uuid.UUID | None = None,
                    q: Annotated[str | None, Query(max_length=100)] = None,
                    limit: Annotated[int, Query(ge=1, le=50)] = 20, station_id: uuid.UUID | None = None) -> list[dict]:
    """People the user could choose: a new case's lead or supervisor (who work at the case's station), or someone to
    add to a case's team (who works at the case's station)."""
    with Audited(db, audit, user, "cm.colleagues.find", "cm_case", case_id, purpose=purpose) as event:
        family = get_family(db, user, case_id) if purpose == "team" and case_id else None
        if family is not None:
            event.target_id = family.display_id
        result = colleagues.candidates(db, user, purpose, classification=classification, family=family, q=q, limit=limit,
                                       station_id=station_id)
        event.read(count=len(result))  # the search text itself is not recorded
    return result


# ---------------------------------------------------------------- dashboards


@router.get("/contributions/mine", response_model=s.MyContributions)
def my_contributions(user: CurrentUser, db: DbSession, audit: Audit, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> dict:
    with Audited(db, audit, user, "cm.contributions.mine", "cm_case") as event:
        result = overview.my_contributions(db, user, limit=limit)
        event.read(count=len(result["entries"]))
    return result


@router.get("/admin/overview", response_model=s.AdminOverview)
def admin_overview(user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    with Audited(db, audit, user, "cm.admin.overview", "cm_case") as event:
        _require_admin(user)
        result = overview.admin_overview(db, user)
        event.read()
    return result


# ---------------------------------------------------------------- live notices (Server-Sent Events)


WatchParam = Annotated[str | None, Query(
    max_length=60, pattern=stream.WATCH_PATTERN,
    description="The page the browser has open (`case:<id>`, `evidence:<id>` or `admin`): the stream then also says when what "
                "that page shows has changed (event `activity`)")]


@router.get("/notifications/stream", response_class=StreamingResponse,
            responses={200: {"content": {"text/event-stream": {}},
                             "description": "Events `notices`, `activity` (with `watch`), `expired` and `reconnect`"}})
def notification_stream(request: Request, token: Annotated[str | None, Depends(oauth2_scheme)], audit: Audit,
                        sessions: Annotated[Callable[[], Session], Depends(get_session_factory)],
                        watch: WatchParam = None) -> StreamingResponse:
    """Tells the browser when the user's notices change (counts only) and, for the page it has open, when what that
    page shows has changed (a fingerprint only: the page then re-reads its data). Without a database connection held open.

    The page's scope follows the same access rules as the page itself, checked at every poll: for a page the user
    may not open, no `activity` event is ever sent (as for one that doesn't exist)."""
    user_id = read_access_token(token) if token else None
    wanted = stream.parse_watch(watch)
    with sessions() as db:
        user = db.get(User, user_id) if user_id else None
        if user is None or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
        with Audited(db, audit, user, "cm.notifications.stream", "cm_notification", watch=wanted.label if wanted else None) as event:
            event.read()

    def state() -> dict | None:
        if read_access_token(token) != user_id:  # the login expired
            return None
        with sessions() as db:
            current: User | None = db.get(User, user_id)
            if current is None or not current.is_active:
                return None
            result = stream.notice_state(db, user_id)
            if wanted is not None:
                result["activity"] = stream.activity_marker(db, current, wanted)
            return result

    every = stream.ADMIN_ACTIVITY_SECONDS if wanted is not None and wanted.kind == "admin" else 0.0
    return StreamingResponse(stream.events(state, request.is_disconnected, scope=wanted.label if wanted else None, activity_every=every),
                             media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- case links


@router.get("/cases/{case_id}/links", response_model=s.CaseLinks)
def case_links(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit, access: Access) -> dict:
    """The case's links (withdrawn ones marked), and the cases that link to it."""
    with Audited(db, audit, user, "cm.links.read", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        result = links.links_of(db, user, family, access)
        event.read(outgoing=len(result["outgoing"]), incoming=len(result["incoming"]))
    return result


@router.post("/cases/{case_id}/links", response_model=s.LinkAdded, status_code=status.HTTP_201_CREATED)
def add_case_link(case_id: uuid.UUID, body: s.LinkCreate, user: CurrentUser, db: DbSession, audit: Audit, access: Access,
                  idempotency_key: IdempotencyKeyHeader = None):
    """Link this case to another one the user can open, or to a past case they may see, with a reason."""
    with Audited(db, audit, user, "cm.link.add", "cm_case", case_id, link_type=body.link_type.value) as event:
        once = Once(db, user, idempotency_key, f"POST /api/v1/cases/{case_id}/links", body.model_dump(mode="json"))
        if (previous := once.previous()) is not None:
            event.read(replayed=True)
            return previous
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        artifact, link = links.add_link(db, user, family, target_case_id=body.target_case_id, knowledge_case=body.knowledge_case,
                                        access=access, link_type=body.link_type.value, reason=body.reason)
        from app.casemgmt import history

        result = {"link_id": link.id, "artifact_id": artifact.id, "display_id": artifact.display_id,
                  "entry": history.last_entry(db, family.id).seq}
        once.save(status.HTTP_201_CREATED, s.LinkAdded, result)
        event.write(link=artifact.display_id)
    return result


# ---------------------------------------------------------------- report preview


@router.get("/cases/{case_id}/report-preview", response_model=s.ReportPreview)
def report_preview(case_id: uuid.UUID, user: CurrentUser, db: DbSession, audit: Audit) -> dict:
    """What a report on the case as it stands contains, with provenance and integrity information (a preview)."""
    with Audited(db, audit, user, "cm.report.preview", "cm_case", case_id) as event:
        family = get_family(db, user, case_id)
        event.target_id = family.display_id
        result = report.report_preview(db, user, family)
        event.read(evidence=len(result["evidence"]), withheld=result["withheld_entries"])
    return result
