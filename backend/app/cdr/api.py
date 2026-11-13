"""CDR Analysis API routes under /api/v1/cdr/."""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.auth.dependencies import CurrentUser
from app.casemgmt.access import get_family, rights
from app.cdr import analytics, export as cdr_export, import_service, llm_search as cdr_llm
from app.cdr.models import CdrImportBatch, CdrCustodyEvent
from app.cdr.schemas import (
    CallGraph, CdrRecordList, CdrSummary, HourFrequency, ImportBatchCreate, ImportBatchOut, TopContact
)
from app.db.session import get_db

router = APIRouter(prefix="/v1/cdr", tags=["CDR Analysis"])
DbSession = Annotated[Session, Depends(get_db)]


def _get_case(case_id: uuid.UUID, user, db: Session):
    """Resolve case_id to a CaseFamily the user may access. Raises NotVisible (→ 404) if not found."""
    return get_family(db, user, case_id)


# ------------------------------------------------------------------ batches


@router.get("/cases/{case_id}/batches", response_model=list[ImportBatchOut])
def list_batches(case_id: uuid.UUID, user: CurrentUser, db: DbSession):
    _get_case(case_id, user, db)
    rows = db.scalars(
        select(CdrImportBatch)
        .where(CdrImportBatch.case_family_id == case_id)
        .order_by(CdrImportBatch.created_at.desc())
    ).all()
    return list(rows)


@router.post("/cases/{case_id}/batches", response_model=ImportBatchOut, status_code=status.HTTP_201_CREATED)
async def upload_cdr(
    case_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    msisdn_rule: str = Form(default="np-msisdn.v1"),
    source_timezone: str = Form(default="Asia/Kathmandu"),
):
    family = _get_case(case_id, user, db)
    r = rights(db, user, family)
    if not r.add_files:
        raise HTTPException(status_code=403, detail="Only case team members with write access may upload CDR files")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("csv", "xls", "xlsx"):
        raise HTTPException(status_code=422, detail="Only CSV, XLS and XLSX files are accepted")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    params = ImportBatchCreate(msisdn_rule=msisdn_rule, source_timezone=source_timezone)

    batch = import_service.receive_file(
        db, user, family.id,
        filename=file.filename or "upload",
        content=content,
        record_format=ext,
        msisdn_rule=params.msisdn_rule,
        source_timezone=params.source_timezone,
    )
    batch = import_service.process_batch(db, batch)
    return batch


@router.get("/cases/{case_id}/batches/{batch_id}", response_model=ImportBatchOut)
def get_batch(case_id: uuid.UUID, batch_id: uuid.UUID, user: CurrentUser, db: DbSession):
    _get_case(case_id, user, db)
    batch = db.get(CdrImportBatch, batch_id)
    if not batch or batch.case_family_id != case_id:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


# ------------------------------------------------------------------ records


@router.get("/cases/{case_id}/records", response_model=CdrRecordList)
def list_records(
    case_id: uuid.UUID, user: CurrentUser, db: DbSession,
    q: str | None = Query(default=None, max_length=200),
    party: str | None = Query(default=None, max_length=50),
    service_type: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    date_from: dt.date | None = Query(default=None),
    date_to: dt.date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    include_duplicates: bool = Query(default=False),
):
    family = _get_case(case_id, user, db)
    total, rows = analytics.search_records(
        db, family.id,
        q=q, party=party,
        service_type=service_type, direction=direction,
        date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
        include_duplicates=include_duplicates,
    )
    return {"total": total, "items": rows}


# ------------------------------------------------------------------ analytics


@router.get("/cases/{case_id}/analytics/summary", response_model=CdrSummary)
def get_summary(case_id: uuid.UUID, user: CurrentUser, db: DbSession):
    family = _get_case(case_id, user, db)
    return analytics.summary_stats(db, family.id)


@router.get("/cases/{case_id}/analytics/top-contacts", response_model=list[TopContact])
def get_top_contacts(case_id: uuid.UUID, user: CurrentUser, db: DbSession, limit: int = Query(default=20, ge=1, le=100)):
    family = _get_case(case_id, user, db)
    return analytics.top_contacts(db, family.id, limit=limit)


@router.get("/cases/{case_id}/analytics/call-graph", response_model=CallGraph)
def get_call_graph(case_id: uuid.UUID, user: CurrentUser, db: DbSession, min_calls: int = Query(default=1, ge=1)):
    family = _get_case(case_id, user, db)
    result = analytics.call_graph(db, family.id, min_calls=min_calls)
    return result


@router.get("/cases/{case_id}/analytics/frequency-by-hour", response_model=list[HourFrequency])
def get_frequency_by_hour(case_id: uuid.UUID, user: CurrentUser, db: DbSession):
    family = _get_case(case_id, user, db)
    return analytics.frequency_by_hour(db, family.id)


# ------------------------------------------------------------------ custody


@router.get("/cases/{case_id}/batches/{batch_id}/custody", response_model=list[dict])
def get_custody(case_id: uuid.UUID, batch_id: uuid.UUID, user: CurrentUser, db: DbSession):
    _get_case(case_id, user, db)
    batch = db.get(CdrImportBatch, batch_id)
    if not batch or batch.case_family_id != case_id:
        raise HTTPException(status_code=404, detail="Batch not found")
    events = db.scalars(
        select(CdrCustodyEvent)
        .where(CdrCustodyEvent.import_batch_id == batch_id)
        .order_by(CdrCustodyEvent.occurred_at)
    ).all()
    return [
        {
            "event_type": e.event_type,
            "occurred_at": e.occurred_at.isoformat(),
            "actor_type": e.actor_type,
            "details": e.details,
        }
        for e in events
    ]


# ------------------------------------------------------------------ Feature 7: Timeline


@router.get("/cases/{case_id}/analytics/timeline", response_model=CdrRecordList)
def get_timeline(
    case_id: uuid.UUID, user: CurrentUser, db: DbSession,
    number: str = Query(..., min_length=3, max_length=30, description="Phone number to show timeline for"),
    date_from: dt.date | None = Query(default=None),
    date_to: dt.date | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
):
    family = _get_case(case_id, user, db)
    records = analytics.timeline_for_number(
        db, family.id, number, date_from=date_from, date_to=date_to, limit=limit
    )
    return {"total": len(records), "items": records}


# ------------------------------------------------------------------ Feature 6: Common contacts


@router.get("/cases/{case_id}/analytics/common-contacts", response_model=dict)
def get_common_contacts(
    case_id: uuid.UUID, user: CurrentUser, db: DbSession,
    a: str = Query(..., min_length=3, max_length=30),
    b: str = Query(..., min_length=3, max_length=30),
):
    family = _get_case(case_id, user, db)
    return analytics.common_contacts(db, family.id, a, b)


# ------------------------------------------------------------------ Feature 10: IMEI associations


@router.get("/cases/{case_id}/analytics/imei-associations", response_model=dict)
def get_imei_associations(case_id: uuid.UUID, user: CurrentUser, db: DbSession):
    family = _get_case(case_id, user, db)
    return analytics.imei_associations(db, family.id)


# ------------------------------------------------------------------ Feature 8: Anomaly detection


@router.get("/cases/{case_id}/analytics/anomalies", response_model=list[dict])
def get_anomalies(case_id: uuid.UUID, user: CurrentUser, db: DbSession):
    family = _get_case(case_id, user, db)
    return analytics.anomaly_detect(db, family.id)


# ------------------------------------------------------------------ Feature 4: Link analysis


@router.get("/cases/{case_id}/analytics/link-graph", response_model=dict)
def get_link_graph(
    case_id: uuid.UUID, user: CurrentUser, db: DbSession,
    number: str = Query(..., min_length=3, max_length=30),
    hops: int = Query(default=2, ge=1, le=3),
    min_calls: int = Query(default=1, ge=1),
):
    family = _get_case(case_id, user, db)
    return analytics.link_graph_for_number(db, family.id, number, hops=hops, min_calls=min_calls)


# ------------------------------------------------------------------ Data profile


@router.get("/cases/{case_id}/data-profile", response_model=dict)
def get_data_profile(case_id: uuid.UUID, user: CurrentUser, db: DbSession):
    family = _get_case(case_id, user, db)
    return analytics.data_profile(db, family.id)


# ------------------------------------------------------------------ AI Search (LLM)


@router.post("/cases/{case_id}/llm-search", response_model=dict)
def llm_search(
    case_id: uuid.UUID, user: CurrentUser, db: DbSession,
    body: dict,
):
    family = _get_case(case_id, user, db)
    query_text = (body.get("query") or "").strip()
    if not query_text:
        raise HTTPException(status_code=422, detail="'query' is required")
    try:
        result = cdr_llm.llm_search(db, family.id, query_text)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"AI search unavailable: {exc}") from exc
    return result


# ------------------------------------------------------------------ Feature 12: Export


@router.get("/cases/{case_id}/export.csv")
def export_csv(case_id: uuid.UUID, user: CurrentUser, db: DbSession):
    family = _get_case(case_id, user, db)
    csv_text = cdr_export.all_records_csv(db, family.id)

    display = getattr(family, "display_id", str(case_id)[:8])
    filename = f"cdr-{display}-{dt.date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([csv_text.encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/cases/{case_id}/export-to-case", response_model=dict, status_code=201)
def export_to_case(case_id: uuid.UUID, user: CurrentUser, db: DbSession):
    family = _get_case(case_id, user, db)
    r = rights(db, user, family)
    if not r.add_files:
        raise HTTPException(status_code=403, detail="Write access required to export CDR to this case")
    result = cdr_export.add_to_case(db, user, family)
    db.commit()
    return result
