"""Excel CDR parser (XLSX/XLS via openpyxl)."""
import io
from typing import Iterator

from openpyxl import load_workbook

from .base import ParsedRow, map_header


def parse_excel(content: bytes) -> Iterator[ParsedRow]:
    wb = load_workbook(filename=io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = iter(ws.rows)
    try:
        header_row = next(rows)
    except StopIteration:
        wb.close()
        return
    columns = [str(cell.value or "").strip() for cell in header_row]
    mapping = map_header(columns)
    for row_num, row in enumerate(rows, start=2):
        raw = {columns[i]: str(cell.value or "").strip() for i, cell in enumerate(row) if i < len(columns)}
        mapped = {field: raw.get(col, "").strip() for field, col in mapping.items()}
        yield ParsedRow(row_number=row_num, raw=raw, mapped=mapped)
    wb.close()
