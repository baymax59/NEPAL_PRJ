"""chat inside a case: the team group and private messages between two members

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-11

Design: docs/case-management/13-plain-case-design.md (section 12). Once a case exists, the people on its team can write to each other: to
the whole team (`recipient_id` empty) or privately to one other member. A message is a permanent, attributed record like everything else in a
case: the database refuses to change or delete one. `case_chat_reads` remembers how far each person has read each conversation (for the
unread counts); that is the only part that changes.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0025'
down_revision: Union[str, Sequence[str], None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "case_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("case_family_id", sa.Uuid(), sa.ForeignKey("case_families.id"), nullable=False),
        sa.Column("sender_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("char_length(btrim(body)) BETWEEN 1 AND 4000", name=op.f("ck_case_messages_body_length")),
        sa.CheckConstraint("recipient_id IS NULL OR recipient_id <> sender_id", name=op.f("ck_case_messages_not_to_oneself")),
    )
    op.create_index("ix_case_messages_case", "case_messages", ["case_family_id", "id"])
    op.create_index("ix_case_messages_direct", "case_messages", ["case_family_id", "sender_id", "recipient_id", "id"])
    op.execute("CREATE TRIGGER cm_case_messages_permanent BEFORE UPDATE OR DELETE ON case_messages FOR EACH ROW EXECUTE FUNCTION cm_forbid_change()")

    op.create_table(
        "case_chat_reads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("case_family_id", sa.Uuid(), sa.ForeignKey("case_families.id"), nullable=False),
        sa.Column("thread", sa.String(40), nullable=False),  # "group", or the id of the other person
        sa.Column("last_read_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "case_family_id", "thread", name=op.f("uq_case_chat_reads_user_id_case_family_id_thread")),
    )


def downgrade() -> None:
    op.drop_table("case_chat_reads")
    op.execute("DROP TRIGGER IF EXISTS cm_case_messages_permanent ON case_messages")
    op.drop_table("case_messages")
