"""Import an authorised police-records export (Step 14.4). TEMPLATE: the field list is a placeholder.

Run from the backend folder:
    uv run python -m scripts.police_import --folder <export folder> --authorisation "<who authorised it, reference>" --dry-run
    uv run python -m scripts.police_import --folder <export folder> --authorisation "<who authorised it, reference>"

--dry-run checks every row and reports, without copying or storing anything.
Otherwise the export folder (records.csv and the FIR documents) is copied to data/police_raw/<folder name>/
and imported. The authorisation text is stored with the import run and in the audit log.
Then, as for the Supreme Court data: scripts.process_documents, embed_chunks, extract_provisions, extract_timeline.
"""

import argparse
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from app.audit.log import AuditLog
from app.connectors.base import RecordFailure
from app.connectors.police_records.connector import PoliceRecordsConnector
from app.connectors.police_records.export_format import ExportFormat, FormatError
from app.connectors.police_records.fields import RAW_DIR
from app.core.config import get_settings
from app.core.enums import AuditOutcome
from app.db.session import SessionLocal
from app.ingestion.pipeline import run_import

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$")


def report(connector: PoliceRecordsConnector) -> None:
    """What an import would do. Prints case IDs and column-level messages, never names or narratives."""
    sensitivity, warnings, failures = Counter(), Counter(), []
    for item in connector.iter_records():
        if isinstance(item, RecordFailure):
            failures.append(f"{item.source_ref}: {item.reason}")
            continue
        sensitivity[item.sensitivity.value] += 1
        print(f"  {item.display_id:24s} {item.sensitivity.value:13s} documents {len(item.documents)}  warnings {len(item.warnings)}")
        warnings.update(item.warnings)
    print(f"Would import {sum(sensitivity.values())} record(s): {dict(sensitivity)}; {len(failures)} could not be read")
    for failure in failures:
        print(f"  not imported: {failure}")
    for warning, count in warnings.items():
        print(f"  warning ({count}x): {warning}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder", required=True, type=Path, help="the export folder, holding records.csv")
    parser.add_argument("--authorisation", required=True, help="who authorised this import, and their reference")
    parser.add_argument("--dry-run", action="store_true", help="check and report only")
    parser.add_argument("--replace", action="store_true", help="replace an earlier copy of the same export folder")
    args = parser.parse_args()

    source = args.folder.resolve()
    try:
        fmt = ExportFormat.for_folder(source)  # format.json in the folder, if the export needs one
    except FormatError as exc:
        sys.exit(str(exc))
    if not (source / fmt.records_file).is_file():
        sys.exit(f"{source / fmt.records_file} not found")
    if not SAFE_NAME.fullmatch(source.name):
        sys.exit("The export folder's name may contain only letters, digits, '.', '_' and '-'")
    if len(args.authorisation.strip()) < 5:
        sys.exit("--authorisation must say who authorised the import (and their reference)")

    if args.dry_run:
        with tempfile.TemporaryDirectory() as scratch:  # read a copy: nothing is stored
            shutil.copytree(source, Path(scratch) / RAW_DIR / source.name)
            report(PoliceRecordsConnector(Path(scratch), source.name))
        return

    settings = get_settings()
    target = settings.data_dir / RAW_DIR / source.name
    if target.resolve() != source:
        if target.exists() and not args.replace:
            sys.exit(f"{target} already exists. Use --replace to import this export again.")
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(source, target)

    connector = PoliceRecordsConnector(settings.data_dir, source.name)
    parameters = {"export": source.name, "authorisation": args.authorisation.strip()}
    with SessionLocal() as session:
        run = run_import(session, connector, parameters=parameters)
    AuditLog(client_ip="police-import").record(
        "ingestion.import",
        AuditOutcome.SUCCESS if run.status != "failed" else AuditOutcome.ERROR,
        username="system:police_import",
        target_type="ingestion_run",
        target_id=str(run.id),
        details={**parameters, **{k: v for k, v in run.stats.items() if k != "failures"}},
    )
    stats = run.stats
    print(f"Run {run.id}: {run.status}")
    print(f"  seen {stats['seen']} | created {stats['created']} | updated {stats['updated']} | "
          f"failed {stats['failed']} | with warnings {stats['with_warnings']}")
    for failure in stats["failures"][:10]:
        print(f"  failed: {failure['source_ref']}: {failure['reason']}")
    print("Next: uv run python -m scripts.process_documents, then embed_chunks, extract_provisions, extract_timeline")


if __name__ == "__main__":
    main()
