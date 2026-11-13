"""CSV CDR parser."""
import csv
import io
from typing import Iterator

from .base import ParsedRow, map_header


def parse_csv(content: bytes, encoding: str = "utf-8-sig") -> Iterator[ParsedRow]:
    text = content.decode(encoding, errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return
    mapping = map_header(list(reader.fieldnames))
    for row_num, raw in enumerate(reader, start=2):
        mapped = {field: raw.get(col, "").strip() for field, col in mapping.items()}
        yield ParsedRow(row_number=row_num, raw=dict(raw), mapped=mapped)
