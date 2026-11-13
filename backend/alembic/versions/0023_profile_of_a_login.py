"""the profile of a login: email, phone and job title, filled in by the person, with the time it was last updated

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-11

Design: docs/case-management/13-plain-case-design.md (section 12). A person creates their login (or is given one) and then fills in
their own profile: email, phone and job title. The name, officer ID, rank and station stay what the officer register says. All
optional; existing accounts start with an empty profile.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0023'
down_revision: Union[str, Sequence[str], None] = '0022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(200), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(40), nullable=True))
    op.add_column("users", sa.Column("job_title", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("profile_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for column in ("profile_updated_at", "job_title", "phone", "email"):
        op.drop_column("users", column)
