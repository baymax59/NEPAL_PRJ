#!/bin/sh
# Restore a backup made by backup.sh (Step 14.3).
#
#   docker compose --profile backup run --rm backup /deploy/restore.sh check <backup>
#       Restores into a temporary database, compares row counts with the backup, deletes it again.
#       Changes nothing: run it after every backup you may need to rely on.
#
#   docker compose --profile backup run --rm backup /deploy/restore.sh apply <backup>
#       REPLACES the database (PGDATABASE) and the uploads with the backup. Stop the application first:
#       docker compose --profile app stop backend web
#
# <backup> is a folder name in BACKUP_DIR, e.g. 2026-11-06T101500Z.
set -eu

mode=${1:-}
name=${2:-}
if [ -z "$mode" ] || [ -z "$name" ]; then
    echo "usage: restore.sh check|apply <backup folder name>" >&2
    exit 2
fi
dir="/backups/$name"
[ -d "$dir" ] || { echo "No backup folder $name" >&2; exit 1; }

echo "Checking files against SHA256SUMS:"
(cd "$dir" && sha256sum -c SHA256SUMS)

case "$mode" in
check)
    scratch=restore_check
    psql --no-psqlrc -q -d postgres -c "drop database if exists $scratch" -c "create database $scratch"
    pg_restore --no-owner --exit-on-error --dbname="$scratch" "$dir/database.dump"
    echo "Rows per table (at backup / restored):"
    status=0
    while read -r table expected; do
        actual=$(psql --no-psqlrc -At -d "$scratch" -c "select count(*) from public.\"$table\"")
        if [ "$actual" = "$expected" ]; then mark=ok; else mark=DIFFERENT; status=1; fi
        printf '  %-28s %9s %9s  %s\n' "$table" "$expected" "$actual" "$mark"
    done < "$dir/row-counts.txt"
    echo "Uploads archive: $(tar -tzf "$dir/uploads.tar.gz" | grep -c -v '/$') file(s), readable"
    echo "Web server archive: $(tar -tzf "$dir/caddy-data.tar.gz" | grep -c -v '/$') file(s), readable"
    psql --no-psqlrc -q -d postgres -c "drop database $scratch"
    if [ "$status" -eq 0 ]; then
        echo "Restore check passed: $name"
        # A marker the readiness check (scripts.readiness_check) looks for: this backup was proven restorable.
        date -u +%Y-%m-%dT%H:%M:%SZ > "$dir/RESTORE_CHECK_PASSED"
    else
        echo "Restore check FAILED: $name" >&2
    fi
    exit "$status"
    ;;
apply)
    echo "Replacing database '$PGDATABASE' and all uploads with backup $name"
    pg_restore --clean --if-exists --no-owner --exit-on-error --dbname="$PGDATABASE" "$dir/database.dump"
    uploads=${RESTORE_UPLOADS_DIR:-/appdata}
    find "$uploads" -mindepth 1 -delete
    tar -xzf "$dir/uploads.tar.gz" -C "$uploads"
    echo "Restored. Caddy's state is in caddy-data.tar.gz if the web server's volume was lost too."
    echo "Start the application: docker compose --profile app up -d"
    ;;
*)
    echo "usage: restore.sh check|apply <backup folder name>" >&2
    exit 2
    ;;
esac
