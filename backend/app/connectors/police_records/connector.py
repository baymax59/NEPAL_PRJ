"""SourceConnector for an authorised police-records export (Step 14.4, TEMPLATE).

Reads data/police_raw/<export folder>/records.csv. Use scripts/police_import.py, which also records who
authorised the import.
"""

import csv
import datetime as dt
import hashlib
import io
from collections.abc import Iterator
from pathlib import Path

from app.connectors.base import RecordFailure, SourceConnector
from app.connectors.police_records.export_format import ExportFormat
from app.connectors.police_records.fields import CONNECTOR_VERSION, RAW_DIR, SOURCE_SYSTEM
from app.connectors.police_records.mapping import ExportInfo, map_row
from app.schemas.case_record import CaseRecord


class PoliceRecordsConnector(SourceConnector):
    source_system = SOURCE_SYSTEM
    version = CONNECTOR_VERSION

    def __init__(self, data_dir: Path, export_name: str, fmt: ExportFormat | None = None):
        self.folder = f"{RAW_DIR}/{export_name}"
        # The export's layout: format.json in its folder, or the template's own (export_format.py).
        self.fmt = fmt or ExportFormat.for_folder(data_dir / self.folder)
        self.records_file = data_dir / self.folder / self.fmt.records_file
        if not self.records_file.exists():
            raise FileNotFoundError(f"{self.records_file} not found")

    def iter_records(self) -> Iterator[CaseRecord | RecordFailure]:
        content = self.records_file.read_bytes()
        export = ExportInfo(
            folder=self.folder,
            file_name=self.fmt.records_file,
            sha256=hashlib.sha256(content).hexdigest(),
            retrieved_at=dt.datetime.fromtimestamp(self.records_file.stat().st_mtime, dt.UTC),
        )
        # utf-8-sig: Excel adds an invisible marker at the start of CSV files it saves. newline="": the
        # csv module itself handles line breaks inside quoted fields (an FIR narrative may have them).
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
        for number, row in enumerate(reader, start=1):  # "record 3" = the third row after the header
            source_ref = f"{self.fmt.records_file} record {number}"
            yield map_row(self.fmt.rename(row), export=export, source_ref=source_ref, fmt=self.fmt)
