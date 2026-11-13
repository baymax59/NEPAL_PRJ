"""Check every stored evidence file against the fingerprint recorded when it was added (phase CM-2).

Run from the backend folder (database running), for example daily as a scheduled task:
    uv run python -m scripts.verify_evidence --by admin

Every result is recorded (administrators see the latest under GET /api/v1/admin/evidence-integrity), and the
run is written to the audit log. Exit code 0 when every file matches; 1 when any file is changed or missing,
so a scheduler can raise an alarm. A failure is never "repaired": the stored file stays as found, for
examination (docs/steps/15-2-evidence.md, section 10).
"""

import argparse
import sys

from sqlalchemy import select

from app.audit.log import AuditLog
from app.casemgmt import evidence
from app.casemgmt.enums import IntegrityResult, OrgRole
from app.casemgmt.models import CaseFamily, EvidenceItem, EvidenceVersion
from app.casemgmt.storage import get_evidence_store
from app.core.enums import AuditOutcome
from app.db.models import User
from app.db.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--by", required=True, help="the platform administrator running the check (recorded as the checker)")
    args = parser.parse_args()

    with SessionLocal() as session:
        admin = session.scalar(select(User).where(User.username == args.by))
        if admin is None or not admin.is_active or admin.org_role != OrgRole.SUPER_ADMIN:
            sys.exit("--by must name an active platform administrator")
        checks = evidence.sweep(session, get_evidence_store(), admin)
        session.commit()
        failed = [c for c in checks if c.result != IntegrityResult.MATCH]
        exhibits = session.execute(
            select(EvidenceVersion.object_sha256, CaseFamily.display_id, EvidenceItem.display_id)
            .join(EvidenceItem, EvidenceItem.id == EvidenceVersion.evidence_item_id)
            .join(CaseFamily, CaseFamily.id == EvidenceItem.case_family_id)
            .where(EvidenceVersion.object_sha256.in_([c.object_sha256 for c in failed]))
        ).all() if failed else []

    counts = {result.value: sum(c.result == result for c in checks) for result in IntegrityResult}
    AuditLog(client_ip="cli").record("cm.evidence.integrity_sweep", AuditOutcome.SUCCESS, username=args.by,
                                     target_type="cm_evidence", details={"checked": len(checks), **counts})
    print(f"Checked {len(checks)} stored file(s): {counts['match']} match, {counts['mismatch']} changed, {counts['missing']} missing.")
    for check in failed:
        used_by = ", ".join(f"{case}/{item}" for sha, case, item in exhibits if sha == check.object_sha256) or "no exhibit"
        print(f"  {check.result.upper()}: {check.object_sha256[:16]}…  ({used_by})")
    if failed:
        print("Do not repair or replace these files: report them, and keep the server as it is for examination.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
