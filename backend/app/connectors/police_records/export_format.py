"""How a particular police export is laid out: an optional format.json in the export folder.

When the real export arrives, most differences from the placeholder template are settings, not code:
the file name, what each column is called, how dates are written, how "yes" is written. For example:

    {
      "records_file": "fir_register_2026.csv",
      "columns": {"fir_number": "FIR No", "fir_year": "Year", "police_station_code": "PS Code"},
      "date_formats": ["%d/%m/%Y"],
      "yes_values": ["Y", "Yes"]
    }

"columns" maps a template field (fields.FIELDS) to the column name used in the export; fields left out
keep their template names. scripts/police_inspect.py suggests this file from a real export.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.connectors.police_records.fields import DATE_FORMATS, FIELDS, RECORDS_FILE, YES

FORMAT_FILE = "format.json"


class FormatError(ValueError):
    """format.json can't be used; the message says why."""


@dataclass(frozen=True)
class ExportFormat:
    records_file: str = RECORDS_FILE
    columns: dict[str, str] = field(default_factory=dict)  # template field -> column name in the export
    date_formats: tuple[str, ...] = DATE_FORMATS
    yes_values: frozenset[str] = frozenset(YES)

    @classmethod
    def load(cls, path: Path) -> "ExportFormat":
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FormatError(f"{path.name} can't be read as JSON ({type(exc).__name__})") from exc
        unknown_keys = set(data) - {"records_file", "columns", "date_formats", "yes_values", "_comment"}
        if unknown_keys:
            raise FormatError(f"{path.name}: unknown setting(s) {', '.join(sorted(unknown_keys))}")
        columns = data.get("columns", {})
        unknown_fields = set(columns) - set(FIELDS)
        if unknown_fields:
            raise FormatError(f"{path.name}: {', '.join(sorted(unknown_fields))} is not a template field (see fields.py)")
        records_file = data.get("records_file", RECORDS_FILE)
        if "/" in records_file or "\\" in records_file or records_file.startswith("."):
            raise FormatError(f"{path.name}: records_file must be a plain file name inside the export folder")
        return cls(
            records_file=records_file,
            columns={key: str(value) for key, value in columns.items()},
            date_formats=tuple(data.get("date_formats", DATE_FORMATS)),
            yes_values=frozenset(str(v).lower() for v in data.get("yes_values", YES)),
        )

    @classmethod
    def for_folder(cls, folder: Path) -> "ExportFormat":
        """format.json in the export folder, or the template's own layout if there is none."""
        file = folder / FORMAT_FILE
        return cls.load(file) if file.exists() else cls()

    def column_for(self, template_field: str) -> str:
        return self.columns.get(template_field, template_field)

    def rename(self, row: dict[str, Any]) -> dict[str, Any]:
        """The row with the export's column names replaced by the template's. Other columns are kept as they are."""
        mapped = {self.column_for(f): f for f in FIELDS}
        return {mapped.get(column, column): value for column, value in row.items()}
