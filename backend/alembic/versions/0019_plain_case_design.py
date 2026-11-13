"""the plain case design: folders, files, a team and a history chain instead of repositories, branches and commits

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-10

Design: docs/case-management/13-plain-case-design.md (phase G-2).

What it does:
- Refuses to run if any case exists: the git-style tables are dropped, and nothing is converted (the user emptied the cases first).
  Take a database backup first, as before.
- Drops the git-style tables: case_repositories, repository_clone_events, repository_branches, branch_head_events, commit_snapshots,
  snapshot_entries, repository_commits, commit_parents, repository_active_assignments, repository_members, contributor_invitations,
  review_requests, review_decisions; and every column that pointed at them (evidence_versions, authorization_events, case_links,
  case_status_events, comments, integration_imports, investigation_tasks, notifications, report_exports).
- Creates case_folders (permanent), case_members (status only: who is on a case, in which part), case_entries (the history chain of a
  case: permanent, and the database accepts only the next entry in order).
- Artifacts and evidence items get a folder and a status (active / withdrawn, with who, when and why): a wrong file is withdrawn, never deleted.
- report_exports names the history entry the report describes (subject_entry_seq) instead of a commit.
- The trigger functions (cm_forbid_change, cm_status_only...) stay: the downgrade, and other tables, use them.

The downgrade puts the git-style tables back, empty, from alembic/old_git_schema_0018.sql (made with pg_dump from the 0018 database).
It also refuses to run if any case exists.
"""
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0019'
down_revision: Union[str, Sequence[str], None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Written out here, not imported from the app: a migration must keep meaning what it meant when written.
MEMBER_ROLES = "'lead', 'sub_investigator', 'analyst', 'viewer'"
HISTORY_KINDS = ("'case_registered', 'folder_added', 'note_added', 'note_revised', 'evidence_added', 'file_withdrawn', 'file_sealed', "
                 "'file_unsealed', 'status_changed', 'reference_added', 'member_added', 'member_removed', 'lead_changed', 'link_added', "
                 "'import_added', 'timeline_generated', 'report_generated'")
FILE_STATUSES = "'active', 'withdrawn'"
OLD_GIT_TABLES = ("review_decisions", "review_requests", "contributor_invitations", "repository_members", "repository_active_assignments",
                  "commit_parents", "snapshot_entries", "repository_commits", "commit_snapshots", "branch_head_events",
                  "repository_branches", "repository_clone_events", "case_repositories")
OLD_SCHEMA = Path(__file__).resolve().parents[1] / "old_git_schema_0018.sql"

CASE_ENTRY_IS_NEXT = """
    CREATE FUNCTION cm_case_entry_is_next() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
        last_seq integer;
        last_hash varchar(64);
    BEGIN
        SELECT seq, entry_hash INTO last_seq, last_hash FROM case_entries
            WHERE case_family_id = NEW.case_family_id ORDER BY seq DESC LIMIT 1;
        IF NEW.seq IS DISTINCT FROM COALESCE(last_seq, 0) + 1 OR NEW.prev_hash IS DISTINCT FROM last_hash THEN
            RAISE EXCEPTION 'Case Management: a history entry must be exactly the next one of its case'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$
"""


def _no_cases(what: str) -> None:
    if op.get_bind().execute(sa.text("SELECT count(*) FROM case_families")).scalar():
        raise RuntimeError(f"Migration 0019 {what} can only run when there are no cases: back up the database and remove them first "
                           "(docs/case-management/13-plain-case-design.md).")


def upgrade() -> None:
    """Upgrade schema."""
    _no_cases("(the plain case design)")

    # --- the new tables
    op.create_table('case_folders',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('case_family_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('system', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('added_by', sa.Uuid(), nullable=False),
    sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['added_by'], ['users.id'], name=op.f('fk_case_folders_added_by_users')),
    sa.ForeignKeyConstraint(['case_family_id'], ['case_families.id'], name=op.f('fk_case_folders_case_family_id_case_families')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_case_folders'))
    )
    op.create_index(op.f('ix_case_folders_case_family_id'), 'case_folders', ['case_family_id'], unique=False)
    op.execute("CREATE UNIQUE INDEX uq_case_folders_name ON case_folders (case_family_id, lower(name))")

    op.create_table('case_members',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('case_family_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('granted_by', sa.Uuid(), nullable=False),
    sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('revoked_by', sa.Uuid(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(f"role IN ({MEMBER_ROLES})", name=op.f('ck_case_members_role_allowed')),
    sa.ForeignKeyConstraint(['case_family_id'], ['case_families.id'], name=op.f('fk_case_members_case_family_id_case_families')),
    sa.ForeignKeyConstraint(['granted_by'], ['users.id'], name=op.f('fk_case_members_granted_by_users')),
    sa.ForeignKeyConstraint(['revoked_by'], ['users.id'], name=op.f('fk_case_members_revoked_by_users')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_case_members_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_case_members'))
    )
    op.create_index(op.f('ix_case_members_case_family_id'), 'case_members', ['case_family_id'], unique=False)
    op.create_index(op.f('ix_case_members_user_id'), 'case_members', ['user_id'], unique=False)
    op.create_index('uq_case_members_one_active', 'case_members', ['case_family_id', 'user_id'], unique=True,
                    postgresql_where=sa.text('revoked_at IS NULL'))
    op.create_index('uq_case_members_one_lead', 'case_members', ['case_family_id'], unique=True,
                    postgresql_where=sa.text("role = 'lead' AND revoked_at IS NULL"))

    op.create_table('case_entries',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('case_family_id', sa.Uuid(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('subject_type', sa.String(length=24), nullable=True),
    sa.Column('subject_id', sa.String(length=64), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('details', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('prev_hash', sa.String(length=64), nullable=True),
    sa.Column('entry_hash', sa.String(length=64), nullable=False),
    sa.CheckConstraint(f"kind IN ({HISTORY_KINDS})", name=op.f('ck_case_entries_kind_allowed')),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_case_entries_actor_id_users')),
    sa.ForeignKeyConstraint(['case_family_id'], ['case_families.id'], name=op.f('fk_case_entries_case_family_id_case_families')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_case_entries')),
    sa.UniqueConstraint('case_family_id', 'seq', name=op.f('uq_case_entries_case_family_id_seq'))
    )
    op.create_index(op.f('ix_case_entries_case_family_id'), 'case_entries', ['case_family_id'], unique=False)

    # --- what pointed at the git-style tables
    op.execute("DROP TRIGGER cm_evidence_versions_in_case ON evidence_versions")
    op.drop_column('evidence_versions', 'commit_id')
    op.drop_column('evidence_versions', 'branch_id')
    op.drop_column('evidence_versions', 'repository_id')
    op.drop_index('ix_authorization_events_repository', table_name='authorization_events')
    op.drop_column('authorization_events', 'repository_id')
    op.create_index('ix_authorization_events_case', 'authorization_events', ['case_family_id', 'id'], unique=False)
    for column in ('commit_id', 'branch_id', 'repository_id', 'path'):
        op.drop_column('case_links', column)
        op.drop_column('integration_imports', column)
    op.drop_column('case_status_events', 'repository_id')
    op.drop_index('ix_comments_target', table_name='comments')
    op.drop_column('comments', 'repository_id')
    op.create_index('ix_comments_target', 'comments', ['case_family_id', 'target_type', 'target_id'], unique=False)
    op.drop_constraint(op.f('ck_comments_target_type_allowed'), 'comments', type_='check')
    op.create_check_constraint(op.f('ck_comments_target_type_allowed'), 'comments', "target_type IN ('case', 'evidence', 'artifact', 'task')")
    op.drop_constraint(op.f('ck_case_status_events_field_allowed'), 'case_status_events', type_='check')
    op.create_check_constraint(op.f('ck_case_status_events_field_allowed'), 'case_status_events', "field IN ('workflow', 'official', 'seal')")
    op.drop_index('ix_investigation_tasks_repository_id', table_name='investigation_tasks')
    for column in ('commit_id', 'branch_id', 'repository_id'):
        op.drop_column('investigation_tasks', column)
    op.create_index(op.f('ix_investigation_tasks_case_family_id'), 'investigation_tasks', ['case_family_id'], unique=False)
    op.drop_column('notifications', 'repository_id')
    for column in ('subject_commit_id', 'commit_id', 'branch_id', 'repository_id'):
        op.drop_column('report_exports', column)
    op.add_column('report_exports', sa.Column('subject_entry_seq', sa.Integer(), nullable=False))

    # --- the git-style tables go (their triggers go with them; the trigger functions stay)
    op.execute("DROP TABLE " + ", ".join(OLD_GIT_TABLES) + " CASCADE")

    # --- files: a folder and a status (withdrawn, never deleted)
    for table, status_only in (("artifacts", "'sealed', 'sealed_reason', 'sealed_by', 'sealed_at'"),
                               ("evidence_items", "'sealed', 'sealed_reason', 'sealed_by', 'sealed_at'")):
        op.execute(f"DROP TRIGGER cm_{table}_status_only ON {table}")
        op.add_column(table, sa.Column('folder_id', sa.Uuid(), nullable=False))
        op.add_column(table, sa.Column('status', sa.String(length=16), server_default='active', nullable=False))
        op.add_column(table, sa.Column('withdrawn_reason', sa.Text(), nullable=True))
        op.add_column(table, sa.Column('withdrawn_by', sa.Uuid(), nullable=True))
        op.add_column(table, sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True))
        op.create_foreign_key(op.f(f'fk_{table}_folder_id_case_folders'), table, 'case_folders', ['folder_id'], ['id'])
        op.create_foreign_key(op.f(f'fk_{table}_withdrawn_by_users'), table, 'users', ['withdrawn_by'], ['id'])
        op.create_index(op.f(f'ix_{table}_folder_id'), table, ['folder_id'], unique=False)
        op.create_check_constraint(op.f(f'ck_{table}_status_allowed'), table, f"status IN ({FILE_STATUSES})")
        op.execute(f"CREATE TRIGGER cm_{table}_status_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION "
                   f"cm_status_only({status_only}, 'status', 'withdrawn_reason', 'withdrawn_by', 'withdrawn_at')")

    # --- permanent records, and the rule that the history only grows by its next entry
    op.execute(CASE_ENTRY_IS_NEXT)
    op.execute("CREATE TRIGGER cm_case_folders_permanent BEFORE UPDATE OR DELETE ON case_folders FOR EACH ROW EXECUTE FUNCTION cm_forbid_change()")
    op.execute("CREATE TRIGGER cm_case_entries_permanent BEFORE UPDATE OR DELETE ON case_entries FOR EACH ROW EXECUTE FUNCTION cm_forbid_change()")
    op.execute("CREATE TRIGGER cm_case_entries_in_order BEFORE INSERT ON case_entries FOR EACH ROW EXECUTE FUNCTION cm_case_entry_is_next()")
    op.execute("CREATE TRIGGER cm_case_members_status_only BEFORE UPDATE OR DELETE ON case_members "
               "FOR EACH ROW EXECUTE FUNCTION cm_status_only('revoked_by', 'revoked_at')")
    op.execute("SELECT cm_grant_runtime()")


def downgrade() -> None:
    """Downgrade schema: the git-style tables come back, empty."""
    _no_cases("(going back to the git-style design)")

    # --- files lose their folder and status
    for table in ("evidence_items", "artifacts"):
        op.execute(f"DROP TRIGGER cm_{table}_status_only ON {table}")
        op.drop_constraint(op.f(f'ck_{table}_status_allowed'), table, type_='check')
        op.drop_index(op.f(f'ix_{table}_folder_id'), table_name=table)
        for column in ('withdrawn_at', 'withdrawn_by', 'withdrawn_reason', 'status', 'folder_id'):
            op.drop_column(table, column)
        op.execute(f"CREATE TRIGGER cm_{table}_status_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION "
                   "cm_status_only('sealed', 'sealed_reason', 'sealed_by', 'sealed_at')")

    # --- the git-style tables, from the dump of the 0018 database
    schema = "\n".join(line for line in OLD_SCHEMA.read_text(encoding="utf-8").splitlines() if not line.startswith("--"))
    op.get_bind().exec_driver_sql(schema)

    # --- the columns that pointed at them (the tables are empty, so NOT NULL is possible)
    op.add_column('evidence_versions', sa.Column('repository_id', sa.Uuid(), nullable=False))
    op.add_column('evidence_versions', sa.Column('branch_id', sa.Uuid(), nullable=False))
    op.add_column('evidence_versions', sa.Column('commit_id', sa.String(length=64), nullable=False))
    op.create_foreign_key(op.f('fk_evidence_versions_repository_id_case_repositories'), 'evidence_versions', 'case_repositories', ['repository_id'], ['id'])
    op.create_foreign_key(op.f('fk_evidence_versions_branch_id_repository_branches'), 'evidence_versions', 'repository_branches', ['branch_id'], ['id'])
    op.create_foreign_key(op.f('fk_evidence_versions_commit_id_repository_commits'), 'evidence_versions', 'repository_commits', ['commit_id'], ['id'])
    op.execute("CREATE TRIGGER cm_evidence_versions_in_case BEFORE INSERT ON evidence_versions "
               "FOR EACH ROW EXECUTE FUNCTION cm_evidence_version_in_its_case()")

    op.drop_index('ix_authorization_events_case', table_name='authorization_events')
    op.add_column('authorization_events', sa.Column('repository_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_authorization_events_repository_id_case_repositories'), 'authorization_events', 'case_repositories', ['repository_id'], ['id'])
    op.create_index('ix_authorization_events_repository', 'authorization_events', ['repository_id', 'id'], unique=False)

    for table in ('case_links', 'integration_imports'):
        op.add_column(table, sa.Column('repository_id', sa.Uuid(), nullable=False))
        op.add_column(table, sa.Column('branch_id', sa.Uuid(), nullable=False))
        op.add_column(table, sa.Column('commit_id', sa.String(length=64), nullable=False))
        op.add_column(table, sa.Column('path', sa.String(length=500), nullable=False))
        op.create_foreign_key(op.f(f'fk_{table}_repository_id_case_repositories'), table, 'case_repositories', ['repository_id'], ['id'])
        op.create_foreign_key(op.f(f'fk_{table}_branch_id_repository_branches'), table, 'repository_branches', ['branch_id'], ['id'])
        op.create_foreign_key(op.f(f'fk_{table}_commit_id_repository_commits'), table, 'repository_commits', ['commit_id'], ['id'])

    op.add_column('case_status_events', sa.Column('repository_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_case_status_events_repository_id_case_repositories'), 'case_status_events', 'case_repositories', ['repository_id'], ['id'])
    op.drop_constraint(op.f('ck_case_status_events_field_allowed'), 'case_status_events', type_='check')
    op.create_check_constraint(op.f('ck_case_status_events_field_allowed'), 'case_status_events',
                               "field IN ('workflow', 'official', 'clone', 'branch', 'review', 'seal')")

    op.drop_index('ix_comments_target', table_name='comments')
    op.add_column('comments', sa.Column('repository_id', sa.Uuid(), nullable=False))
    op.create_foreign_key(op.f('fk_comments_repository_id_case_repositories'), 'comments', 'case_repositories', ['repository_id'], ['id'])
    op.create_index('ix_comments_target', 'comments', ['repository_id', 'target_type', 'target_id'], unique=False)
    op.drop_constraint(op.f('ck_comments_target_type_allowed'), 'comments', type_='check')
    op.create_check_constraint(op.f('ck_comments_target_type_allowed'), 'comments', "target_type IN ('commit', 'evidence', 'artifact', 'review', 'task')")

    op.drop_index(op.f('ix_investigation_tasks_case_family_id'), table_name='investigation_tasks')
    op.add_column('investigation_tasks', sa.Column('repository_id', sa.Uuid(), nullable=False))
    op.add_column('investigation_tasks', sa.Column('branch_id', sa.Uuid(), nullable=True))
    op.add_column('investigation_tasks', sa.Column('commit_id', sa.String(length=64), nullable=True))
    op.create_foreign_key(op.f('fk_investigation_tasks_repository_id_case_repositories'), 'investigation_tasks', 'case_repositories', ['repository_id'], ['id'])
    op.create_foreign_key(op.f('fk_investigation_tasks_branch_id_repository_branches'), 'investigation_tasks', 'repository_branches', ['branch_id'], ['id'])
    op.create_foreign_key(op.f('fk_investigation_tasks_commit_id_repository_commits'), 'investigation_tasks', 'repository_commits', ['commit_id'], ['id'])
    op.create_index('ix_investigation_tasks_repository_id', 'investigation_tasks', ['repository_id'], unique=False)

    op.add_column('notifications', sa.Column('repository_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_notifications_repository_id_case_repositories'), 'notifications', 'case_repositories', ['repository_id'], ['id'])

    op.drop_column('report_exports', 'subject_entry_seq')
    op.add_column('report_exports', sa.Column('repository_id', sa.Uuid(), nullable=False))
    op.add_column('report_exports', sa.Column('branch_id', sa.Uuid(), nullable=False))
    op.add_column('report_exports', sa.Column('commit_id', sa.String(length=64), nullable=False))
    op.add_column('report_exports', sa.Column('subject_commit_id', sa.String(length=64), nullable=False))
    op.create_foreign_key(op.f('fk_report_exports_repository_id_case_repositories'), 'report_exports', 'case_repositories', ['repository_id'], ['id'])
    op.create_foreign_key(op.f('fk_report_exports_branch_id_repository_branches'), 'report_exports', 'repository_branches', ['branch_id'], ['id'])
    op.create_foreign_key(op.f('fk_report_exports_commit_id_repository_commits'), 'report_exports', 'repository_commits', ['commit_id'], ['id'])
    op.create_foreign_key(op.f('fk_report_exports_subject_commit_id_repository_commits'), 'report_exports', 'repository_commits', ['subject_commit_id'], ['id'])

    # --- the plain-design tables go
    op.drop_table('case_entries')
    op.drop_table('case_members')
    op.drop_table('case_folders')
    op.execute("DROP FUNCTION cm_case_entry_is_next()")
    op.execute("SELECT cm_grant_runtime()")
