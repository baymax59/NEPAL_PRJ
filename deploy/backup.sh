#!/bin/sh
# Back up the database, the uploads and the web server's state (Step 14.3).
#
#   docker compose --profile backup run --rm backup
#
# Writes BACKUP_DIR/<UTC time>/ with:
#   database.dump      the whole database (pg_dump custom format: compressed, restorable table by table)
#   uploads.tar.gz     uploaded "new case" files
#   caddy-data.tar.gz  Caddy's state, including its certificate authority's private key
#   row-counts.txt     rows per table, to check a restore against
#   SHA256SUMS         checksums, to detect damaged or altered files
# and deletes backups older than BACKUP_KEEP_DAYS (default 14).
#
# Backups contain everything the application holds. Keep them as protected as the database itself:
# an encrypted disk, not a synced folder, plus a copy in a second place (docs/steps/14-3-*).
set -eu

stamp=$(date -u +%Y-%m-%dT%H%M%SZ)
dir="/backups/$stamp"
mkdir -p "$dir"
echo "Backing up to $stamp/"

pg_dump --format=custom --file="$dir/database.dump"
for table in $(psql --no-psqlrc -At -c "select tablename from pg_tables where schemaname = 'public' order by 1"); do
    printf '%s %s\n' "$table" "$(psql --no-psqlrc -At -c "select count(*) from public.\"$table\"")"
done > "$dir/row-counts.txt"
tar -czf "$dir/uploads.tar.gz" -C /appdata .
tar -czf "$dir/caddy-data.tar.gz" -C /caddy_data .
(cd "$dir" && sha256sum database.dump uploads.tar.gz caddy-data.tar.gz row-counts.txt > SHA256SUMS)

ls -l "$dir" | tail -n +2
echo "Tables: $(wc -l < "$dir/row-counts.txt"), rows: $(awk '{ s += $2 } END { print s }' "$dir/row-counts.txt")"

keep=${BACKUP_KEEP_DAYS:-14}
old=$(find /backups -mindepth 1 -maxdepth 1 -type d -name '20*Z' -mtime +"$keep")
if [ -n "$old" ]; then
    echo "Removing backups older than $keep days:"
    echo "$old"
    echo "$old" | xargs rm -rf
fi
echo "Done: $stamp"
