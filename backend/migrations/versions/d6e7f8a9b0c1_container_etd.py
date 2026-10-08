"""containers.etd — data wypłynięcia z trackingu (pierwsze zdarzenie DEPART)

Revision ID: d6e7f8a9b0c1
Revises: c4d5e6f7a8b9
Create Date: 2026-09-01
"""
import sqlalchemy as sa
from alembic import op

revision = 'd6e7f8a9b0c1'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('containers', sa.Column('etd', sa.Date(), nullable=True))
    # backfill z już zapisanych zdarzeń trackingu (najwcześniejszy DEPART per kontener)
    op.execute("""
        UPDATE containers SET etd = (
            SELECT MIN(DATE(te.occurred_at)) FROM tracking_events te
            WHERE te.container_id = containers.id AND te.event_code = 'DEPART'
              AND te.occurred_at IS NOT NULL)
        WHERE etd IS NULL
    """)


def downgrade() -> None:
    op.drop_column('containers', 'etd')
