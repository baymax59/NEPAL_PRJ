"""The interface every data-source connector implements.

A connector is the only code that knows a source's format. It reads source records and
yields CaseRecords; the ingestion pipeline (app/ingestion/pipeline.py) stores them.
A future police-records connector implements this same interface.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import ClassVar

from app.schemas.case_record import CaseRecord


@dataclass(frozen=True)
class RecordFailure:
    """A source record that could not be converted. It is reported, never silently dropped."""

    source_ref: str  # where in the source it is, e.g. "metadata.parquet row 17"
    reason: str


class SourceConnector(ABC):
    source_system: ClassVar[str]  # stored on every case, e.g. "sc_judgments"
    version: ClassVar[str]  # bump when the mapping changes, so imports are traceable

    @abstractmethod
    def iter_records(self) -> Iterator[CaseRecord | RecordFailure]:
        """Yield each source record as a CaseRecord, or a RecordFailure saying why it couldn't be."""
