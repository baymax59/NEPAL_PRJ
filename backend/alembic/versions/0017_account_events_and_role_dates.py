"""account and role events in the access history, and the date a role took effect

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-10

Design: docs/case-management/12-roles-and-stations.md (phase R-3).

- authorization_events (the permanent access history) may now also record: an account created, a role changed
  (promotion or demotion), a station granted or revoked.
- users.org_role_since: the moment the user's current role took effect. Empty means "from the start". It makes the
  promotion rule possible: powers that come from the role itself reach only cases registered since that moment.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0017'
down_revision: Union[str, Sequence[str], None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Written out here, not imported from the app: a migration must keep meaning what it meant when written.
OLD_CHANGES = "'membership_granted', 'membership_revoked'"
NEW_CHANGES = OLD_CHANGES + ", 'account_created', 'role_changed', 'station_granted', 'station_revoked'"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('org_role_since', sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint(op.f('ck_authorization_events_change_allowed'), 'authorization_events', type_='check')
    op.create_check_constraint(op.f('ck_authorization_events_change_allowed'), 'authorization_events', f"change IN ({NEW_CHANGES})")


def downgrade() -> None:
    """Downgrade schema (development only). Events of the new kinds can't be deleted (they are permanent), so the old
    rule is added without checking the rows that already exist."""
    op.drop_constraint(op.f('ck_authorization_events_change_allowed'), 'authorization_events', type_='check')
    op.execute(f"ALTER TABLE authorization_events ADD CONSTRAINT ck_authorization_events_change_allowed "
               f"CHECK (change IN ({OLD_CHANGES})) NOT VALID")
    op.drop_column('users', 'org_role_since')
