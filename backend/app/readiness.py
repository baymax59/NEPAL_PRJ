"""Go-live readiness: the decisions in docs/DECISIONS.md, plus what a computer can check by itself.

Used by scripts/readiness_check.py. Each check says what is wrong and which decision it belongs to.
"""

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path

SYNCED_FOLDERS = ("onedrive", "dropbox", "google drive", "googledrive", "icloud")
DECISION = re.compile(r"^## (?P<id>D\d+)\. (?P<title>.+?)$.*?^\*\*Status:\*\* *(?P<status>\w+)", re.M | re.S)


@dataclass(frozen=True)
class Check:
    name: str
    done: bool
    detail: str


def decisions(form: Path) -> list[Check]:
    """One check per decision in the sign-off form: done when its status says "decided"."""
    if not form.exists():
        return [Check("docs/DECISIONS.md", False, "the sign-off form is missing")]
    return [
        Check(f"{m['id']} {m['title']}", m["status"].lower() == "decided", f"status: {m['status']}")
        for m in DECISION.finditer(form.read_text(encoding="utf-8"))
    ]


def is_synced(path: Path) -> bool:
    return any(name in str(path).lower() for name in SYNCED_FOLDERS)


def read_env(env_file: Path) -> dict[str, str]:
    """KEY=value lines of .env (values are only compared, never printed)."""
    if not env_file.exists():
        return {}
    pairs = (line.split("=", 1) for line in env_file.read_text(encoding="utf-8").splitlines() if "=" in line and not line.lstrip().startswith("#"))
    return {key.strip(): value.strip() for key, value in pairs}


def latest_backup(backup_dir: Path) -> Path | None:
    folders = sorted(p for p in backup_dir.glob("20*Z") if p.is_dir()) if backup_dir.exists() else []
    return folders[-1] if folders else None


def technical_checks(project: Path, env: dict[str, str], *, labels: dict, connector_version: str,
                     audit_retention_days: int | None, dev_accounts_in_use: list[str], now: dt.datetime,
                     evidence_root: Path | None = None, worker_last_run: dt.datetime | None = None,
                     demo_case: str | None = None, demo_accounts_active: list[str] | None = None) -> list[Check]:
    evidence_root = evidence_root or project / "data" / "evidence"
    checks = [
        Check("Project folder not in a cloud-synced folder (D12)", not is_synced(project), str(project)),
        # Write-once protection itself can't be checked from here: it is part of decision D14.
        Check("Evidence store outside cloud-synced folders (D14)", not is_synced(evidence_root), str(evidence_root)),
    ]

    backup_dir = (project / env.get("BACKUP_DIR", "./backups")).resolve()
    latest = latest_backup(backup_dir)
    checks.append(Check("Backups stored outside cloud-synced folders (D8)", not is_synced(backup_dir), str(backup_dir)))
    if latest is None:
        checks.append(Check("A recent backup exists (D8)", False, "no backup found"))
        checks.append(Check("The latest backup was proven restorable (D8)", False, "no backup found"))
    else:
        taken = dt.datetime.strptime(latest.name, "%Y-%m-%dT%H%M%SZ").replace(tzinfo=dt.UTC)
        age = now - taken
        checks.append(Check("A recent backup exists (D8)", age <= dt.timedelta(hours=48), f"{latest.name}, {age.days} day(s) old"))
        checks.append(Check("The latest backup was proven restorable (D8)", (latest / "RESTORE_CHECK_PASSED").exists(),
                            "restore.sh check passed" if (latest / "RESTORE_CHECK_PASSED").exists() else f"run: restore.sh check {latest.name}"))

    checks.append(Check("Audit log retention period set (D4)", audit_retention_days is not None,
                        f"AUDIT_RETENTION_DAYS={audit_retention_days}" if audit_retention_days else "not set: audit entries kept indefinitely"))

    tls = env.get("TLS", "internal")
    checks.append(Check("Certificate from the organisation (D7)", tls != "internal",
                        "TLS=internal: Caddy's own authority (fine for testing)" if tls == "internal" else "organisation certificate configured"))
    caddyfile = project / "deploy" / "Caddyfile"
    hsts = caddyfile.exists() and re.search(r"^\s*Strict-Transport-Security", caddyfile.read_text(encoding="utf-8"), re.M)
    checks.append(Check("HTTPS-only enforced in browsers (HSTS) (D7)", bool(hsts), "on" if hsts else "commented out in deploy/Caddyfile"))

    checks.append(Check("Development accounts removed or passwords changed (D5)", not dev_accounts_in_use,
                        "still usable with the passwords in .dev-credentials.txt: " + ", ".join(dev_accounts_in_use) if dev_accounts_in_use else "none in use"))

    jwt, audit, db = env.get("JWT_SECRET", ""), env.get("AUDIT_SECRET", ""), env.get("POSTGRES_PASSWORD", "")
    strong = len(jwt) >= 32 and len(audit) >= 32 and jwt != audit and len(db) >= 16 and "change-me" not in (jwt + audit + db)
    checks.append(Check("Secrets different, long and not the examples", strong, "ok" if strong else "see .env.example"))

    review = labels.get("review", {})
    reviewed, total = review.get("items_fully_reviewed", 0), review.get("items_total") or len(labels.get("queries", [])) + len(labels.get("similar_cases", []))
    checks.append(Check("Search-quality labels reviewed by a legal expert (D9)", total > 0 and reviewed == total,
                        f"{reviewed} of {total} queries fully reviewed" + (f" (by {review['reviewer']})" if review.get("reviewer") else "")))

    template = connector_version.endswith("-template")
    checks.append(Check("Police connector adapted to the real export (D2)", not template,
                        f"version {connector_version}: placeholder field list" if template else f"version {connector_version}"))

    security_doc = project / "docs" / "SECURITY_REVIEW.md"
    checks.append(Check("Internal security review written (D11 input)", security_doc.exists(), "docs/SECURITY_REVIEW.md"))

    # Case Management governance (phase CM-7, decision D16). Values are only measured or compared, never printed.
    mfa = env.get("CM_MFA_REQUIRED", "").lower() == "true"
    checks.append(Check("Two-step verification required for administrators and supervisors (D16)", mfa,
                        "CM_MFA_REQUIRED=true" if mfa else "set CM_MFA_REQUIRED=true once they have set it up"))
    checks.append(Check("Audit checkpoint key set, held apart from the database administrators (D16)",
                        len(env.get("CM_CHECKPOINT_KEY", "")) >= 32, "set" if len(env.get("CM_CHECKPOINT_KEY", "")) >= 32
                        else "CM_CHECKPOINT_KEY not set: checkpoints are signed with a key derived from AUDIT_SECRET"))
    checks.append(Check("Key for two-step verification secrets set (D16)", len(env.get("MFA_KEY", "")) >= 32,
                        "set" if len(env.get("MFA_KEY", "")) >= 32 else "MFA_KEY not set: derived from JWT_SECRET"))
    own_login = len(env.get("POSTGRES_APP_PASSWORD", "")) >= 16
    checks.append(Check("The application uses its own database login, without DELETE (D16)", own_login,
                        "POSTGRES_APP_USER / POSTGRES_APP_PASSWORD set" if own_login else "not set: the owner login is used"))
    test_source_off = env.get("CM_TEST_SOURCE", "true").lower() == "false"
    checks.append(Check("Fictional test source turned off (D16)", test_source_off,
                        "CM_TEST_SOURCE=false" if test_source_off else "still on: set CM_TEST_SOURCE=false"))
    recent = worker_last_run is not None and now - worker_last_run <= dt.timedelta(hours=48)
    checks.append(Check("The worker's daily checks ran in the last 48 hours (D16)", recent,
                        f"last run {worker_last_run:%Y-%m-%d %H:%M} UTC" if worker_last_run else "no run recorded: start the worker"))

    # The fictional demonstration (phase CM-8) belongs in development and training databases only. Case records can't be
    # deleted, so a production database that holds it must be replaced by a fresh one before real records go in.
    checks.append(Check("No fictional demonstration case in this database (CM-8)", demo_case is None,
                        "none" if demo_case is None else f"{demo_case} (FICTIONAL demonstration) is here: real records need a fresh "
                                                         "database, as case records can't be deleted"))
    active = demo_accounts_active or []
    checks.append(Check("Fictional demonstration accounts deactivated (CM-8)", not active,
                        "none active" if not active else f"active: {', '.join(active)} (scripts.create_user <name> --deactivate)"))
    return checks


def load_labels(project: Path) -> dict:
    file = project / "backend" / "evaluation" / "labels.json"
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
