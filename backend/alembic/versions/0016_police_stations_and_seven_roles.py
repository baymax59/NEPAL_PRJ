"""police stations, the officer registry and the seven roles

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-10

Design: docs/case-management/12-roles-and-stations.md (phase R-2).

What it does:
- police_stations, user_stations, officer_registry (never deleted; only the named columns may change).
- case_families.station_id: every existing case goes to a default station "HQ" of its organisation. The trigger that
  allows only status changes is paused for that one fill-in and recreated with the same columns (station_id then can't change).
- users.officer_id (empty for accounts made before this migration).
- The role names: platform_admin becomes super_admin (it already saw the whole organisation); administrator and
  sub_investigator are new. Past audit events keep the old name: history is not rewritten.
- Every existing account except a Super Admin is assigned to HQ, so what it can see does not change.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Written out here, not imported from the app: a migration must keep meaning what it meant when written.
OLD_ROLES = "'platform_admin', 'supervisor', 'investigator', 'analyst', 'viewer'"
NEW_ROLES = "'super_admin', 'administrator', 'supervisor', 'investigator', 'sub_investigator', 'analyst', 'viewer'"
CASE_FAMILY_CHANGEABLE = "'workflow_status', 'official_status', 'supervisor_id'"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('police_stations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('district', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='active', nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('active', 'inactive')", name=op.f('ck_police_stations_status_allowed')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_police_stations_created_by_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_police_stations_organization_id_organizations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_police_stations')),
    sa.UniqueConstraint('organization_id', 'code', name=op.f('uq_police_stations_organization_id_code'))
    )
    op.create_index(op.f('ix_police_stations_organization_id'), 'police_stations', ['organization_id'], unique=False)

    op.create_table('officer_registry',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('officer_number', sa.String(length=32), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('rank', sa.String(length=64), nullable=False),
    sa.Column('station_id', sa.Uuid(), nullable=False),
    sa.Column('highest_role', sa.String(length=16), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint(f"highest_role IN ({NEW_ROLES})", name=op.f('ck_officer_registry_highest_role_allowed')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_officer_registry_created_by_users')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_officer_registry_organization_id_organizations')),
    sa.ForeignKeyConstraint(['station_id'], ['police_stations.id'], name=op.f('fk_officer_registry_station_id_police_stations')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_officer_registry')),
    sa.UniqueConstraint('organization_id', 'officer_number', name=op.f('uq_officer_registry_organization_id_officer_number'))
    )
    op.create_index(op.f('ix_officer_registry_organization_id'), 'officer_registry', ['organization_id'], unique=False)
    op.create_index(op.f('ix_officer_registry_station_id'), 'officer_registry', ['station_id'], unique=False)

    op.create_table('user_stations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('station_id', sa.Uuid(), nullable=False),
    sa.Column('assigned_by', sa.Uuid(), nullable=True),
    sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('revoked_by', sa.Uuid(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], name=op.f('fk_user_stations_assigned_by_users')),
    sa.ForeignKeyConstraint(['revoked_by'], ['users.id'], name=op.f('fk_user_stations_revoked_by_users')),
    sa.ForeignKeyConstraint(['station_id'], ['police_stations.id'], name=op.f('fk_user_stations_station_id_police_stations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_stations_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_stations'))
    )
    op.create_index(op.f('ix_user_stations_user_id'), 'user_stations', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_stations_station_id'), 'user_stations', ['station_id'], unique=False)
    op.create_index('uq_user_stations_active', 'user_stations', ['user_id', 'station_id'], unique=True,
                    postgresql_where=sa.text('revoked_at IS NULL'))

    # The default station of every organisation: existing cases and accounts go there, so nothing is lost or hidden.
    op.execute("""
        INSERT INTO police_stations (id, organization_id, code, name)
        SELECT gen_random_uuid(), id, 'HQ', 'Headquarters (default station)' FROM organizations
    """)

    # case_families.station_id (the trigger of migration 0007 allows only status changes: paused for this one fill-in).
    op.execute("DROP TRIGGER cm_case_families_status_only ON case_families")
    op.add_column('case_families', sa.Column('station_id', sa.Uuid(), nullable=True))
    op.execute("""
        UPDATE case_families c SET station_id =
            (SELECT s.id FROM police_stations s WHERE s.organization_id = c.organization_id AND s.code = 'HQ')
    """)
    op.alter_column('case_families', 'station_id', nullable=False)
    op.create_foreign_key(op.f('fk_case_families_station_id_police_stations'), 'case_families', 'police_stations', ['station_id'], ['id'])
    op.create_index(op.f('ix_case_families_station_id'), 'case_families', ['station_id'], unique=False)
    op.execute("CREATE TRIGGER cm_case_families_status_only BEFORE UPDATE OR DELETE ON case_families "
               f"FOR EACH ROW EXECUTE FUNCTION cm_status_only({CASE_FAMILY_CHANGEABLE})")

    # The seven roles. platform_admin (the whole organisation) is the Super Admin; history is not rewritten.
    op.drop_constraint(op.f('ck_users_org_role_allowed'), 'users', type_='check')
    op.execute("UPDATE users SET org_role = 'super_admin' WHERE org_role = 'platform_admin'")
    op.create_check_constraint(op.f('ck_users_org_role_allowed'), 'users', f"org_role IN ({NEW_ROLES})")
    op.add_column('users', sa.Column('officer_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_users_officer_id_officer_registry'), 'users', 'officer_registry', ['officer_id'], ['id'])
    op.create_unique_constraint(op.f('uq_users_officer_id'), 'users', ['officer_id'])
    op.execute("""
        INSERT INTO user_stations (id, user_id, station_id)
        SELECT gen_random_uuid(), u.id, s.id FROM users u
        JOIN police_stations s ON s.organization_id = u.organization_id AND s.code = 'HQ'
        WHERE u.org_role <> 'super_admin'
    """)

    # Permanent records (functions from migration 0007): never deleted; only these columns change.
    op.execute("CREATE TRIGGER cm_police_stations_status_only BEFORE UPDATE OR DELETE ON police_stations "
               "FOR EACH ROW EXECUTE FUNCTION cm_status_only('name', 'district', 'status')")
    op.execute("CREATE TRIGGER cm_user_stations_status_only BEFORE UPDATE OR DELETE ON user_stations "
               "FOR EACH ROW EXECUTE FUNCTION cm_status_only('revoked_by', 'revoked_at')")
    op.execute("CREATE TRIGGER cm_officer_registry_status_only BEFORE UPDATE OR DELETE ON officer_registry "
               "FOR EACH ROW EXECUTE FUNCTION cm_status_only('full_name', 'rank', 'station_id', 'highest_role')")
    # The restricted database login (no DELETE) gets its rights on the new tables (function from migration 0014).
    op.execute("SELECT cm_grant_runtime()")


def downgrade() -> None:
    """Downgrade schema (development only: station links are lost)."""
    for table in ("officer_registry", "user_stations", "police_stations"):
        op.execute(f"DROP TRIGGER IF EXISTS cm_{table}_status_only ON {table}")
    op.drop_constraint(op.f('uq_users_officer_id'), 'users', type_='unique')
    op.drop_constraint(op.f('fk_users_officer_id_officer_registry'), 'users', type_='foreignkey')
    op.drop_column('users', 'officer_id')
    op.drop_constraint(op.f('ck_users_org_role_allowed'), 'users', type_='check')
    op.execute("UPDATE users SET org_role = CASE org_role WHEN 'super_admin' THEN 'platform_admin' "
               "WHEN 'administrator' THEN 'supervisor' WHEN 'sub_investigator' THEN 'investigator' ELSE org_role END")
    op.create_check_constraint(op.f('ck_users_org_role_allowed'), 'users', f"org_role IN ({OLD_ROLES})")
    op.execute("DROP TRIGGER cm_case_families_status_only ON case_families")
    op.drop_index(op.f('ix_case_families_station_id'), table_name='case_families')
    op.drop_constraint(op.f('fk_case_families_station_id_police_stations'), 'case_families', type_='foreignkey')
    op.drop_column('case_families', 'station_id')
    op.execute("CREATE TRIGGER cm_case_families_status_only BEFORE UPDATE OR DELETE ON case_families "
               f"FOR EACH ROW EXECUTE FUNCTION cm_status_only({CASE_FAMILY_CHANGEABLE})")
    op.drop_index('uq_user_stations_active', table_name='user_stations', postgresql_where=sa.text('revoked_at IS NULL'))
    op.drop_index(op.f('ix_user_stations_station_id'), table_name='user_stations')
    op.drop_index(op.f('ix_user_stations_user_id'), table_name='user_stations')
    op.drop_table('user_stations')
    op.drop_index(op.f('ix_officer_registry_station_id'), table_name='officer_registry')
    op.drop_index(op.f('ix_officer_registry_organization_id'), table_name='officer_registry')
    op.drop_table('officer_registry')
    op.drop_index(op.f('ix_police_stations_organization_id'), table_name='police_stations')
    op.drop_table('police_stations')
