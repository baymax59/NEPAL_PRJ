"""manifest.json: a record of exactly which files were downloaded, from where, when, and their checksums.

The download script writes it; the connector reads it. It makes the subset reproducible and
gives every imported case its provenance.
"""

import datetime as dt
from pathlib import Path

from pydantic import BaseModel


class FileEntry(BaseModel):
    key: str  # bucket key, which is also the path under data/raw/sc_judgments/
    source_uri: str
    sha256: str
    size_bytes: int
    retrieved_at: dt.datetime


class Manifest(BaseModel):
    seed: int = 42
    metadata: dict[int, FileEntry] = {}  # year -> metadata.parquet
    selected: dict[int, list[str]] = {}  # year -> `path` values of the rows chosen for the subset
    pdfs: dict[str, FileEntry] = {}  # `path` -> judgment PDF
    failed: dict[str, str] = {}  # `path` -> why its PDF could not be downloaded

    @classmethod
    def load(cls, file: Path) -> "Manifest":
        if not file.exists():
            return cls()
        return cls.model_validate_json(file.read_text(encoding="utf-8"))

    def save(self, file: Path) -> None:
        file.parent.mkdir(parents=True, exist_ok=True)
        tmp = file.with_suffix(".tmp")
        tmp.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(file)  # atomic: an interrupted save never leaves a half-written manifest
