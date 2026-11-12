"""Look at a real police export before importing it, and suggest its format.json (Step 14.4 follow-up).

Meant for the first meeting with the data owner: which template fields the export has and under what
names, how dates are written, what code values occur, duplicates, missing documents. It never shows
personal data: for personal and unrecognised columns only counts are reported, never values.
"""

import csv
import datetime as dt
import io
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.connectors.police_records.export_format import ExportFormat
from app.connectors.police_records.fields import DATE_FORMATS, FIELDS, ID_FIELDS, YES
from app.connectors.police_records.mapping import SAFE_DOCUMENT

PERSONAL = {"complainant_name", "accused_names", "investigating_officer", "brief_facts"}
CODES = {"investigation_status", "final_report_type", "sensitivity", "protected_identity", "police_station_code",
         "police_station_name", "district"}
DATES = {"registration_date", "occurrence_date", "final_report_date"}
MAX_VALUES = 20

# Date layouts worth recognising in exports. Two-digit years are left out on purpose: the century would be a guess.
CANDIDATE_DATE_FORMATS = DATE_FORMATS + (
    "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d",
    "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
)

# Other names the same field often has, written without spaces, underscores or capitals.
SYNONYMS = {
    "fir_number": ["firno", "firnumber", "fir", "firnum"],
    "fir_year": ["year", "firyear", "regyear", "registrationyear"],
    "police_station_code": ["pscode", "stationcode", "policestationcode", "psid"],
    "police_station_name": ["psname", "policestation", "stationname", "policestationname", "ps"],
    "district": ["dist", "districtname"],
    "registration_date": ["regdate", "firdate", "dateofregistration", "registereddate", "registrationdate"],
    "occurrence_date": ["dateofoccurrence", "incidentdate", "offencedate", "occurrencedate"],
    "acts_sections": ["actsections", "acts", "sections", "actandsections", "undersections"],
    "complainant_name": ["complainant", "informant", "informantname"],
    "accused_names": ["accused", "accusedname"],
    "investigating_officer": ["io", "ioname", "investigatingofficer"],
    "investigation_status": ["status", "casestatus"],
    "final_report_type": ["finalreport", "frtype", "disposal"],
    "final_report_date": ["frdate", "chargesheetdate", "finalreportdate"],
    "brief_facts": ["facts", "gist", "briefoffacts", "narrative"],
    "sensitivity": ["classification"],
    "protected_identity": ["protected", "identityprotected", "victimidentityprotected"],
    "fir_document": ["document", "firfile", "file", "filename"],
}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _date_format(value: str) -> str | None:
    for fmt in CANDIDATE_DATE_FORMATS:
        try:
            dt.datetime.strptime(value, fmt)
            return fmt
        except ValueError:
            continue
    return None


def suggest_columns(header: list[str], fmt: ExportFormat) -> dict[str, str | None]:
    """Template field -> the export column that probably holds it (None: not found)."""
    by_norm = {_norm(column): column for column in header}
    found: dict[str, str | None] = {}
    for field in FIELDS:
        column = fmt.column_for(field)
        if column in header:
            found[field] = column
            continue
        names = [_norm(field), *SYNONYMS.get(field, [])]
        found[field] = next((by_norm[n] for n in names if n in by_norm), None)
    return found


def inspect_export(folder: Path, fmt: ExportFormat) -> tuple[list[str], dict[str, Any]]:
    """(report lines, suggested format.json). Raises FileNotFoundError / UnicodeDecodeError for unusable files."""
    raw = (folder / fmt.records_file).read_bytes()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = list(reader.fieldnames or [])
    rows = list(reader)
    count = len(rows) or 1
    lines = [
        f"File: {fmt.records_file}: {len(rows)} row(s), {len(header)} column(s)"
        + (" (with Excel's UTF-8 marker)" if raw.startswith(b"\xef\xbb\xbf") else ""),
        "",
        "Template fields:",
    ]

    columns = suggest_columns(header, fmt)
    detected_dates: Counter[str] = Counter()
    yes_like: set[str] = set()
    for field, column in columns.items():
        if column is None:
            lines.append(f"  {field:22s} NOT FOUND")
            continue
        values = [(row.get(column) or "").strip() for row in rows]
        filled = [v for v in values if v]
        note = f"{100 * (len(values) - len(filled)) / count:3.0f}% empty"
        if field in PERSONAL:
            note += "; personal data: values not shown"
        elif field in DATES:
            formats = Counter(_date_format(v) for v in filled)
            readable = sum(n for f, n in formats.items() if f)
            detected_dates.update({f: n for f, n in formats.items() if f})
            note += f"; dates readable {100 * readable / (len(filled) or 1):.0f}%"
            note += "".join(f", {f} x{n}" for f, n in formats.most_common() if f)
        elif field in CODES:
            distinct = Counter(filled)
            if len(distinct) <= MAX_VALUES:
                note += "; values: " + ", ".join(f"{v!r} x{n}" for v, n in distinct.most_common())
            else:
                note += f"; {len(distinct)} different values"
            if field == "protected_identity":
                yes_like = {v for v in distinct if v.lower() in YES or v.lower() in {"y", "yes", "true", "1", "haan"}}
        elif field == "fir_document":
            present = sum(1 for v in filled if SAFE_DOCUMENT.fullmatch(v) and (folder / v).is_file())
            unsafe = sum(1 for v in filled if not SAFE_DOCUMENT.fullmatch(v))
            note += f"; {present} of {len(filled)} document file(s) present, {unsafe} unusable name(s)"
        renamed = "" if column == field else f"  <- column {column!r}"
        lines.append(f"  {field:22s} found{renamed}; {note}")

    id_columns = [columns[f] for f in ID_FIELDS]
    if all(id_columns):
        keys = Counter(tuple((row.get(c) or "").strip() for c in id_columns) for row in rows)
        missing = sum(n for key, n in keys.items() if not all(key))
        duplicates = sum(n - 1 for key, n in keys.items() if all(key) and n > 1)
        lines += ["", f"Identity (station + year + FIR number): {missing} row(s) incomplete, {duplicates} duplicate(s)"]
    else:
        lines += ["", "Identity: can't be checked until all of police_station_code, fir_year and fir_number are found"]

    used = {c for c in columns.values() if c}
    extra = [c for c in header if c not in used]
    lines += ["", f"Other columns in the export ({len(extra)}), kept as extra information on import; values not shown:"]
    for column in extra:
        values = [(row.get(column) or "").strip() for row in rows]
        filled = [v for v in values if v]
        dates = sum(1 for v in filled if _date_format(v))
        lines.append(
            f"  {column!r}: {100 * (len(values) - len(filled)) / count:.0f}% empty, {len(set(filled))} different values"
            + (f", {100 * dates / len(filled):.0f}% look like dates" if filled and dates else "")
        )

    suggestion: dict[str, Any] = {
        "_comment": "Suggested by scripts.police_inspect; check every line with the data owner, then save as format.json",
    }
    if fmt.records_file != "records.csv":
        suggestion["records_file"] = fmt.records_file
    renames = {f: c for f, c in columns.items() if c and c != f}
    if renames:
        suggestion["columns"] = renames
    if detected_dates and set(detected_dates) - set(DATE_FORMATS):
        suggestion["date_formats"] = [f for f, _ in detected_dates.most_common()]
    if {v.lower() for v in yes_like} - YES:  # only if the export says "yes" in a way the template doesn't know
        suggestion["yes_values"] = sorted(yes_like)
    return lines, suggestion
