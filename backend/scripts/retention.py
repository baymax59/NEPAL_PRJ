"""Delete uploads (and, if configured, audit entries) older than their retention period. Run daily.

Run from the backend folder, or inside Docker:
    uv run python -m scripts.retention --dry-run      # show what would be deleted; deletes nothing
    uv run python -m scripts.retention
    docker compose --profile app run --rm backend python -m scripts.retention
Periods: UPLOAD_RETENTION_DAYS (default 30) and AUDIT_RETENTION_DAYS (default: keep audit entries).
Every run is written to the audit log.
"""

import argparse

from app.audit.log import AuditLog
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.retention import apply_retention


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="only report what is due for deletion")
    args = parser.parse_args()

    settings = get_settings()
    with SessionLocal() as session:
        result = apply_retention(
            session,
            AuditLog(client_ip="retention-job"),
            settings.data_dir,
            settings.upload_retention_days,
            settings.audit_retention_days,
            dry_run=args.dry_run,
        )
    verb = "Due for deletion (dry run, nothing deleted)" if result.dry_run else "Deleted"
    print(f"{verb}: {result.uploads} upload(s) older than {settings.upload_retention_days} days "
          f"(before {result.upload_cutoff:%Y-%m-%d %H:%M} UTC)")
    if result.audit_cutoff:
        print(f"{verb}: {result.audit_events} audit entries older than {settings.audit_retention_days} days")
    else:
        print("Audit entries: kept (AUDIT_RETENTION_DAYS is not set; your organisation decides the period)")


if __name__ == "__main__":
    main()
