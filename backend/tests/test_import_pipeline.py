"""run_import(): storing connector output and keeping a record of each run."""

import pytest
from sqlalchemy import func, select

from app.connectors.base import RecordFailure, SourceConnector
from app.db.models import Case, IngestionRun
from app.ingestion.pipeline import run_import


class FakeConnector(SourceConnector):
    source_system = "test_source"
    version = "0.0.1"

    def __init__(self, items):
        self.items = items

    def iter_records(self):
        for item in self.items:
            if isinstance(item, Exception):
                raise item
            yield item


def case_count(session) -> int:
    return session.scalar(select(func.count()).select_from(Case).where(Case.source_system == "test_source"))


def test_import_stores_records_and_reports_failures(db_session, make_record):
    connector = FakeConnector(
        [
            make_record(source_record_id="A", display_id="TEST-A"),
            RecordFailure("row 2", "Row has no CNR"),
            make_record(source_record_id="B", display_id="TEST-B", warnings=["PDF missing"]),
        ]
    )

    run = run_import(db_session, connector, parameters={"years": [2023]})

    assert run.status == "partial"
    assert run.stats["seen"] == 3
    assert run.stats["created"] == 2
    assert run.stats["failed"] == 1
    assert run.stats["with_warnings"] == 1
    assert run.stats["failures"] == [{"source_ref": "row 2", "reason": "Row has no CNR"}]
    assert run.finished_at is not None
    assert case_count(db_session) == 2
    stored = db_session.scalars(select(Case).where(Case.source_system == "test_source")).all()
    assert {c.last_ingestion_run_id for c in stored} == {run.id}


def test_running_the_same_import_twice_updates_without_duplicating(db_session, make_record):
    records = [make_record(source_record_id=x, display_id=f"TEST-{x}") for x in ("A", "B")]

    run_import(db_session, FakeConnector(records))
    second = run_import(db_session, FakeConnector(records))

    assert second.status == "succeeded"
    assert (second.stats["created"], second.stats["updated"]) == (0, 2)
    assert case_count(db_session) == 2


def test_same_record_twice_in_one_run_is_reported(db_session, make_record):
    record = make_record(source_record_id="A", display_id="TEST-A")

    run = run_import(db_session, FakeConnector([record, record]))

    assert run.stats["created"] == 1
    assert run.stats["failed"] == 1
    assert "twice" in run.stats["failures"][0]["reason"]


def test_one_record_rejected_by_the_database_does_not_stop_the_rest(db_session, make_record):
    connector = FakeConnector(
        [
            make_record(source_record_id="A", display_id="TEST-SAME"),
            make_record(source_record_id="B", display_id="TEST-SAME"),  # display ID clash
            make_record(source_record_id="C", display_id="TEST-C"),
        ]
    )

    run = run_import(db_session, connector)

    assert run.status == "partial"
    assert run.stats["created"] == 2
    assert run.stats["failures"][0]["source_ref"] == "TEST-SAME"
    assert "UniqueViolation" in run.stats["failures"][0]["reason"]
    assert case_count(db_session) == 2


def test_a_crash_is_recorded_on_the_run(db_session, make_record):
    connector = FakeConnector([make_record(), RuntimeError("disk unplugged")])

    with pytest.raises(RuntimeError):
        run_import(db_session, connector)

    run = db_session.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc())).first()
    assert run.status == "failed"
    assert run.error_summary == "RuntimeError: disk unplugged"
