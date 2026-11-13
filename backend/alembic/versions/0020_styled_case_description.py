"""a case can keep a styled copy of its description (bold, colours, lists) next to the plain text

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-11

Design: docs/case-management/13-plain-case-design.md (section 12). The description is written in an editor with a formatting
toolbar. The plain text stays in `description` (reports, search and the assistant read it); the styled copy goes in the new
`description_html`, cleaned by the server before it is stored, and is only used to show the description on the case page.
Existing cases have no styled copy and keep showing their plain text. Adding a column is not a change to a case, so the rule
that allows only status changes on `case_families` is not involved.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0020'
down_revision: Union[str, Sequence[str], None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("case_families", sa.Column("description_html", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("case_families", "description_html")
