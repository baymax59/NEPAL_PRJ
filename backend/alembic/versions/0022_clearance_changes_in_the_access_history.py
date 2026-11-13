"""a person's clearance can be changed, and the change is kept in the access history

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-11

Design: docs/case-management/13-plain-case-design.md (section 12). An officer who creates their own login starts with public
clearance (view-only); a Supervisor or Administrator raises it (and the role) afterwards. Every change is a permanent entry of the
access history, like role and station changes, so the list of allowed kinds of entry gets one more: `clearance_changed`.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0022'
down_revision: Union[str, Sequence[str], None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Written out here, not imported from the app: a migration must keep meaning what it meant when written.
PREVIOUS = ("'membership_granted', 'membership_revoked', 'account_created', 'role_changed', 'station_granted', 'station_revoked', "
            "'password_reset', 'account_deactivated', 'account_reactivated'")
NEWER = PREVIOUS + ", 'clearance_changed'"


def upgrade() -> None:
    op.drop_constraint(op.f('ck_authorization_events_change_allowed'), 'authorization_events', type_='check')
    op.create_check_constraint(op.f('ck_authorization_events_change_allowed'), 'authorization_events', f"change IN ({NEWER})")


def downgrade() -> None:
    """Development only: permanent events of the new kind stay, so the old rule is not checked against them."""
    op.drop_constraint(op.f('ck_authorization_events_change_allowed'), 'authorization_events', type_='check')
    op.execute(f"ALTER TABLE authorization_events ADD CONSTRAINT ck_authorization_events_change_allowed CHECK (change IN ({PREVIOUS})) NOT VALID")
