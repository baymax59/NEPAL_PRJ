"""organisation case-number prefix can be set until the first case

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-07 18:30:00

Decision D13: an organisation chooses the prefix of its case numbers (e.g. "KH" in KH-2026-0001). Case numbers
are permanent, so the prefix may change only while the organisation has no cases. Its name may always change;
nothing else about an organisation changes, and organisations are never deleted.
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TRIGGER cm_organizations_status_only ON organizations")
    op.execute("""
        CREATE FUNCTION cm_organization_rules() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Case Management: DELETE on organizations is not allowed: these records are permanent'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            IF (to_jsonb(OLD) - 'name' - 'code') IS DISTINCT FROM (to_jsonb(NEW) - 'name' - 'code') THEN
                RAISE EXCEPTION 'Case Management: on organizations, only name and code may change'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            IF NEW.code IS DISTINCT FROM OLD.code
               AND EXISTS (SELECT 1 FROM case_families WHERE organization_id = OLD.id) THEN
                RAISE EXCEPTION 'Case Management: organisation % already has cases, so its case-number prefix stays', OLD.code
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("CREATE TRIGGER cm_organizations_rules BEFORE UPDATE OR DELETE ON organizations "
               "FOR EACH ROW EXECUTE FUNCTION cm_organization_rules()")


def downgrade() -> None:
    op.execute("DROP TRIGGER cm_organizations_rules ON organizations")
    op.execute("DROP FUNCTION cm_organization_rules()")
    op.execute("CREATE TRIGGER cm_organizations_status_only BEFORE UPDATE OR DELETE ON organizations "
               "FOR EACH ROW EXECUTE FUNCTION cm_status_only('name')")
