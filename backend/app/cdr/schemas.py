"""Pydantic schemas for the CDR API."""
from __future__ import annotations
import datetime as dt
import uuid

from pydantic import BaseModel, Field, field_validator


class ImportBatchCreate(BaseModel):
    msisdn_rule: str = Field(default="np-msisdn.v1", pattern=r"^(np|in)-msisdn\.v1$")
    source_timezone: str = Field(default="Asia/Kathmandu", max_length=64)

    @field_validator("source_timezone")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        import zoneinfo
        try:
            zoneinfo.ZoneInfo(v)
        except (zoneinfo.ZoneInfoNotFoundError, KeyError):
            raise ValueError(f"Unknown timezone: {v}")
        return v


class ImportBatchOut(BaseModel):
    id: uuid.UUID
    case_family_id: uuid.UUID
    uploaded_by: uuid.UUID
    file_name: str
    file_size_bytes: int
    file_hash_sha256: str
    record_format: str
    msisdn_rule: str
    source_timezone: str
    status: str
    total_rows: int | None
    accepted_rows: int | None
    rejected_rows: int | None
    duplicate_rows: int | None
    import_notes: str | None
    created_at: dt.datetime
    completed_at: dt.datetime | None

    model_config = {"from_attributes": True}


class CdrRecordOut(BaseModel):
    id: uuid.UUID
    import_batch_id: uuid.UUID
    source_row_number: int
    is_duplicate: bool
    a_party: str | None
    b_party: str | None
    a_party_canonical: str | None
    b_party_canonical: str | None
    timestamp_utc: dt.datetime | None
    duration_seconds: int | None
    call_type: str | None
    call_direction: str | None
    service_type: str | None
    imei: str | None
    imsi: str | None
    cell_id: str | None
    area_code: str | None
    operator: str | None
    network_type: str | None
    network_generation: str | None

    model_config = {"from_attributes": True}


class CdrRecordList(BaseModel):
    total: int
    items: list[CdrRecordOut]


class TopContact(BaseModel):
    number: str
    count: int


class GraphNode(BaseModel):
    id: str
    label: str


class GraphEdge(BaseModel):
    source: str
    target: str
    count: int
    types: list[str]


class CallGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class HourFrequency(BaseModel):
    hour: int
    count: int


class CdrSummary(BaseModel):
    total_records: int
    unique_subscribers: int
    earliest: str | None
    latest: str | None
