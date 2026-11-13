"""a new account must set its own password at first login; resets and deactivations in the access history

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-10

Design: docs/case-management/12-roles-and-stations.md (phase R-4). The person who creates an account (or resets a password)
gets a temporary password to hand over once; the account's owner must replace it at their first login, so nobody but the
owner knows the real password. Existing accounts are not affected. A password reset, a deactivation and a reactivation
become permanent records in the access history (authorization_events), like role and station changes.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0018'
down_revision: Union[str, Sequence[str], None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Written out here, not imported from the app: a migration must keep meaning what it meant when written.
PREVIOUS = ("'membership_granted', 'membership_revoked', 'account_created', 'role_changed', 'station_granted', 'station_revoked'")
NEWER = PREVIOUS + ", 'password_reset', 'account_deactivated', 'account_reactivated'"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.drop_constraint(op.f('ck_authorization_events_change_allowed'), 'authorization_events', type_='check')
    op.create_check_constraint(op.f('ck_authorization_events_change_allowed'), 'authorization_events', f"change IN ({NEWER})")


def downgrade() -> None:
    """Downgrade schema (development only; permanent events of the new kinds stay, so the old rule is not checked against them)."""
    op.drop_constraint(op.f('ck_authorization_events_change_allowed'), 'authorization_events', type_='check')
    op.execute(f"ALTER TABLE authorization_events ADD CONSTRAINT ck_authorization_events_change_allowed CHECK (change IN ({PREVIOUS})) NOT VALID")
    op.drop_column('users', 'must_change_password')
