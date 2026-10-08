"""Obserwowanie: powód + data przy gwiazdce kontenera, gwiazdka na statku (watched_vessels).

Revision ID: watch001
Revises: dostalias001
"""
import sqlalchemy as sa
from alembic import op

revision = "watch001"
down_revision = "dostalias001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("watched_containers") as batch:
        batch.add_column(sa.Column("reason", sa.String(200), nullable=False,
                                   server_default=sa.text("''")))
        batch.add_column(sa.Column("created_at", sa.DateTime, nullable=True))
    op.create_table(
        "watched_vessels",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("vessel_id", sa.Integer, sa.ForeignKey("tracked_vessels.id"), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("user_id", "vessel_id"),
    )
    op.create_index("ix_watched_vessels_user_id", "watched_vessels", ["user_id"])
    op.create_index("ix_watched_vessels_vessel_id", "watched_vessels", ["vessel_id"])


def downgrade() -> None:
    op.drop_table("watched_vessels")
    with op.batch_alter_table("watched_containers") as batch:
        batch.drop_column("created_at")
        batch.drop_column("reason")
