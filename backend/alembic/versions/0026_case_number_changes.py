"""the case number can be changed by whoever oversees the case; every change is kept

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-12

Design: docs/case-management/13-plain-case-design.md (section 12, decision 20). `case_families` stays protected by its trigger, which until now
allowed only the statuses and the supervisor to change; now it allows the case number (`display_id`) too. Each change is written in
`case_number_changes`, which the database refuses to change or delete: the old number stays on record, finds the case, and is never given to
another case. The history gets a new kind of entry, `case_renumbered`.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0026'
down_revision: Union[str, Sequence[str], None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_KINDS = ("'case_registered', 'folder_added', 'note_added', 'note_revised', 'evidence_added', 'file_withdrawn', 'file_sealed', "
             "'file_unsealed', 'status_changed', 'reference_added', 'member_added', 'member_removed', 'lead_changed', 'link_added', "
             "'import_added', 'timeline_generated', 'report_generated'")
NEW_KINDS = OLD_KINDS + ", 'case_renumbered'"
BEFORE = "'workflow_status', 'official_status', 'supervisor_id'"
AFTER = BEFORE + ", 'display_id'"


def _trigger(columns: str) -> None:
    op.execute("DROP TRIGGER cm_case_families_status_only ON case_families")
    op.execute("CREATE TRIGGER cm_case_families_status_only BEFORE UPDATE OR DELETE ON case_families "
               f"FOR EACH ROW EXECUTE FUNCTION cm_status_only({columns})")


def _kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_case_entries_kind_allowed"), "case_entries", type_="check")
    op.create_check_constraint(op.f("ck_case_entries_kind_allowed"), "case_entries", f"kind IN ({kinds})")


def upgrade() -> None:
    _kinds(NEW_KINDS)
    op.create_table(
        "case_number_changes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("case_family_id", sa.Uuid(), sa.ForeignKey("case_families.id"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("old_number", sa.String(32), nullable=False),
        sa.Column("new_number", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_case_number_changes_case_family_id"), "case_number_changes", ["case_family_id"])
    op.create_index("ix_case_number_changes_old", "case_number_changes", ["organization_id", "old_number"])
    op.execute("CREATE TRIGGER cm_case_number_changes_permanent BEFORE UPDATE OR DELETE ON case_number_changes "
               "FOR EACH ROW EXECUTE FUNCTION cm_forbid_change()")
    _trigger(AFTER)


def downgrade() -> None:
    _kinds(OLD_KINDS)  # refused by the database if a case still has a "case_renumbered" entry: the history is never rewritten
    _trigger(BEFORE)
    op.execute("DROP TRIGGER cm_case_number_changes_permanent ON case_number_changes")
    op.drop_table("case_number_changes")
