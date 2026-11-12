"""SourceConnector for the downloaded Supreme Court subset.

Reads only local files (manifest + metadata Parquet), so importing works offline and is
repeatable. Run scripts/sc_download.py first.
"""

from collections.abc import Iterator
from pathlib import Path

import pyarrow.parquet as pq

from app.connectors.base import RecordFailure, SourceConnector
from app.connectors.sc_judgments.manifest import Manifest
from app.connectors.sc_judgments.mapping import map_row
from app.connectors.sc_judgments.source import CONNECTOR_VERSION, MANIFEST_NAME, RAW_DIR, SOURCE_SYSTEM
from app.schemas.case_record import CaseRecord


class SupremeCourtConnector(SourceConnector):
    source_system = SOURCE_SYSTEM
    version = CONNECTOR_VERSION

    def __init__(self, data_dir: Path, years: list[int] | None = None):
        self.raw_dir = data_dir / RAW_DIR
        manifest_file = self.raw_dir / MANIFEST_NAME
        if not manifest_file.exists():
            raise FileNotFoundError(f"{manifest_file} not found. Run: uv run python -m scripts.sc_download")
        self.manifest = Manifest.load(manifest_file)
        self.years = years or sorted(self.manifest.selected)

    def iter_records(self) -> Iterator[CaseRecord | RecordFailure]:
        for year in self.years:
            meta = self.manifest.metadata.get(year)
            if meta is None or not (self.raw_dir / meta.key).exists():
                yield RecordFailure(f"year={year}", "Metadata not downloaded for this year")
                continue

            selected = set(self.manifest.selected.get(year, []))
            rows = pq.read_table(self.raw_dir / meta.key).to_pylist()
            for index, row in enumerate(rows):
                path = row.get("path")
                if path not in selected:
                    continue
                pdf = self.manifest.pdfs.get(path)
                pdf_failure = self.manifest.failed.get(path)
                if pdf is not None and not (self.raw_dir / pdf.key).exists():
                    pdf, pdf_failure = None, "downloaded file is missing from the data folder"
                yield map_row(
                    row,
                    metadata_file=meta,
                    pdf=pdf,
                    pdf_failure=pdf_failure,
                    source_ref=f"{meta.key} row {index}",
                )
