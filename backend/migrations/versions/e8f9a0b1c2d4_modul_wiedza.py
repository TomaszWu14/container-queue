"""moduł Wiedza (W16): pinezki wiedzy, tematy do omówienia, noty eskalacyjne

Revision ID: e8f9a0b1c2d4
Revises: a9b8c7d6e5f4
Create Date: 2026-09-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d4'
down_revision: Union[str, Sequence[str], None] = 'a9b8c7d6e5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "knowledge_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope_type", sa.String(30), nullable=False),
        sa.Column("scope_key", sa.String(120), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_knowledge_scope", "knowledge_notes", ["scope_type", "scope_key"])
    op.create_index("ix_knowledge_notes_is_active", "knowledge_notes", ["is_active"])

    op.create_table(
        "training_topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope_type", sa.String(30), nullable=False),
        sa.Column("scope_key", sa.String(120), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="otwarty"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "training_votes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("training_topics.id"),
                  nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("topic_id", "user_id"),
    )
    op.create_index("ix_training_votes_topic_id", "training_votes", ["topic_id"])
    op.create_index("ix_training_votes_user_id", "training_votes", ["user_id"])

    op.create_table(
        "knowledge_bulletins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "bulletin_acks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bulletin_id", sa.Integer(), sa.ForeignKey("knowledge_bulletins.id"),
                  nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("bulletin_id", "user_id"),
    )
    op.create_index("ix_bulletin_acks_bulletin_id", "bulletin_acks", ["bulletin_id"])
    op.create_index("ix_bulletin_acks_user_id", "bulletin_acks", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("bulletin_acks")
    op.drop_table("knowledge_bulletins")
    op.drop_table("training_votes")
    op.drop_table("training_topics")
    op.drop_index("ix_knowledge_scope", table_name="knowledge_notes")
    op.drop_table("knowledge_notes")
