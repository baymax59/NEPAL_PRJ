"""who reported the case: the details of the person, or "unknown"

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-11

Design: docs/case-management/13-plain-case-design.md (section 12). A case can record the person who reported it (name, phone,
email, address). None of it is required: when no one is there at the time, the case says the reporter is unknown
(`reported_by_unknown`). Like the rest of the case's facts, it is written once, when the case is registered. Existing cases
have nothing recorded. Adding columns is not a change to a case, so the rule that allows only status changes on `case_families`
is not involved.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0021'
down_revision: Union[str, Sequence[str], None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("case_families", sa.Column("reported_by_unknown", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("case_families", sa.Column("reported_by_name", sa.String(200), nullable=True))
    op.add_column("case_families", sa.Column("reported_by_phone", sa.String(40), nullable=True))
    op.add_column("case_families", sa.Column("reported_by_email", sa.String(200), nullable=True))
    op.add_column("case_families", sa.Column("reported_by_address", sa.String(500), nullable=True))


def downgrade() -> None:
    for column in ("reported_by_address", "reported_by_email", "reported_by_phone", "reported_by_name", "reported_by_unknown"):
        op.drop_column("case_families", column)
