"""Go-live readiness: decisions from the sign-off form, and the checks a computer can make."""

import datetime as dt

from app.readiness import decisions, technical_checks

NOW = dt.datetime(2026, 11, 7, 12, 0, tzinfo=dt.UTC)
STRONG = {"JWT_SECRET": "j" * 40, "AUDIT_SECRET": "a" * 40, "POSTGRES_PASSWORD": "p" * 20}
REVIEWED = {"review": {"items_fully_reviewed": 32, "items_total": 32, "reviewer": "A. Sharma"}}


def test_decisions_are_read_from_the_sign_off_form(tmp_path):
    form = tmp_path / "DECISIONS.md"
    form.write_text(
        "# Form\n\n## D1. Legal basis\n**Question:** ...\n**Status:** decided\n\n"
        "## D2. The real export\n**Question:** ...\n**Status:** open\n",
        encoding="utf-8",
    )

    checks = decisions(form)

    assert [(c.name, c.done) for c in checks] == [("D1 Legal basis", True), ("D2 The real export", False)]
    assert not decisions(tmp_path / "missing.md")[0].done


def ready_project(tmp_path):
    """A project folder in which everything that can be checked is done."""
    project = tmp_path / "case-search"
    backup = project / "backups" / "2026-11-07T020000Z"
    backup.mkdir(parents=True)
    (backup / "RESTORE_CHECK_PASSED").write_text("2026-11-07T02:05:00Z", encoding="utf-8")
    (project / "deploy").mkdir()
    (project / "deploy" / "Caddyfile").write_text('header {\n\tStrict-Transport-Security "max-age=31536000"\n}\n', encoding="utf-8")
    (project / "docs").mkdir()
    (project / "docs" / "SECURITY_REVIEW.md").write_text("review", encoding="utf-8")
    return project


def run(project, **changes):
    values = dict(env={**STRONG, "TLS": "/certs/site.crt /certs/site.key"}, labels=REVIEWED, connector_version="1.0",
                  audit_retention_days=1825, dev_accounts_in_use=[], now=NOW) | changes
    env = values.pop("env")
    return {c.name: c for c in technical_checks(project, env, **values)}


def test_a_fully_prepared_installation_passes_every_check(tmp_path):
    checks = run(ready_project(tmp_path))

    assert [name for name, check in checks.items() if not check.done] == []


def test_each_open_item_is_reported_with_its_decision(tmp_path):
    synced = tmp_path / "OneDrive" / "Desktop"
    synced.mkdir(parents=True)
    project = ready_project(synced)
    (project / "deploy" / "Caddyfile").write_text('# Strict-Transport-Security "max-age=31536000"\n', encoding="utf-8")
    old = project / "backups" / "2026-11-01T020000Z"
    old.mkdir()
    (project / "backups" / "2026-11-07T020000Z" / "RESTORE_CHECK_PASSED").unlink()
    (project / "backups" / "2026-11-07T020000Z").rmdir()

    checks = run(project, env={**STRONG, "AUDIT_SECRET": STRONG["JWT_SECRET"]}, labels={"queries": [{}] * 28, "similar_cases": [{}] * 4},
                 connector_version="0.1-template", audit_retention_days=None, dev_accounts_in_use=["admin", "analyst"])

    open_items = {name: check.detail for name, check in checks.items() if not check.done}
    assert set(open_items) == {
        "Project folder not in a cloud-synced folder (D12)",
        "Backups stored outside cloud-synced folders (D8)",
        "A recent backup exists (D8)",
        "The latest backup was proven restorable (D8)",
        "Audit log retention period set (D4)",
        "Certificate from the organisation (D7)",
        "HTTPS-only enforced in browsers (HSTS) (D7)",
        "Development accounts removed or passwords changed (D5)",
        "Secrets different, long and not the examples",
        "Search-quality labels reviewed by a legal expert (D9)",
        "Police connector adapted to the real export (D2)",
    }
    assert open_items["A recent backup exists (D8)"] == "2026-11-01T020000Z, 6 day(s) old"
    assert open_items["Search-quality labels reviewed by a legal expert (D9)"] == "0 of 32 queries fully reviewed"
    assert "admin, analyst" in open_items["Development accounts removed or passwords changed (D5)"]
