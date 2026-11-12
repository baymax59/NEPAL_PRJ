"""Look at a police export before importing it: what it contains, and a suggested format.json.

Run from the backend folder:
    uv run python -m scripts.police_inspect --folder <export folder>
    uv run python -m scripts.police_inspect --folder <export folder> --records-file fir_register.csv

Only column names, counts and code values (statuses, report types, ...) are shown, never names,
narratives or values of unrecognised columns. Nothing is stored. See docs/steps/14-4-*.md.
"""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from app.connectors.police_records.export_format import ExportFormat, FormatError
from app.connectors.police_records.inspect import inspect_export


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder", required=True, type=Path, help="the export folder")
    parser.add_argument("--records-file", help="the CSV file's name, if not records.csv (or as in format.json)")
    args = parser.parse_args()

    folder = args.folder.resolve()
    try:
        fmt = ExportFormat.for_folder(folder)
    except FormatError as exc:
        sys.exit(str(exc))
    if args.records_file:
        fmt = replace(fmt, records_file=args.records_file)
    try:
        lines, suggestion = inspect_export(folder, fmt)
    except FileNotFoundError:
        sys.exit(f"{folder / fmt.records_file} not found (use --records-file if it has another name)")
    except UnicodeDecodeError:
        sys.exit(f"{fmt.records_file} is not UTF-8 text: ask for a UTF-8 export (Excel: 'CSV UTF-8')")

    print("\n".join(lines))
    print("\nSuggested format.json (save it in the export folder once checked):")
    print(json.dumps(suggestion, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
