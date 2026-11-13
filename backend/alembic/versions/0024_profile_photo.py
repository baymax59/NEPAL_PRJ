"""a profile photo for each login

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-11

Design: docs/case-management/13-plain-case-design.md (section 12). The person's own photo, already cleaned and made small by the server
(app/auth/photos.py: a 256 x 256 JPEG, no metadata), kept in the database so that backups carry it. The picture itself is
not read with every user (the column is loaded only when the picture is asked for); `photo_updated_at` says whether there is one.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0024'
down_revision: Union[str, Sequence[str], None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("photo_data", sa.LargeBinary(), nullable=True))
    op.add_column("users", sa.Column("photo_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "photo_updated_at")
    op.drop_column("users", "photo_data")
