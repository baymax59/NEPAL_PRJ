"""case management live pages

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-08 12:00:00.000000

Phase CM-8: an index so that the live-page fingerprint (app/casemgmt/stream.py) finds a case's integrity checks
without reading the whole table. Nothing else changes: no table, no rule, no data.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_evidence_integrity_checks_item", "evidence_integrity_checks", ["evidence_item_id", "id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_evidence_integrity_checks_item", table_name="evidence_integrity_checks")
