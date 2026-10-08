"""Dziennik serwera: żądania błędne/wolne, liczniki ruchu per minuta, przebiegi zadań tła.

Revision ID: log001
Revises: avatar001
"""
import sqlalchemy as sa
from alembic import op

revision = "log001"
down_revision = "avatar001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ip", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("request_id", sa.String(16), nullable=False, server_default=sa.text("''")),
        sa.Column("error", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.create_index("ix_request_logs_at", "request_logs", ["at"])
    op.create_index("ix_request_logs_status", "request_logs", ["status"])

    op.create_table(
        "request_counters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("minute", sa.DateTime(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("c4xx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("c5xx", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("dur_ms_sum", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("minute", name="uq_request_counters_minute"),
    )

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job", sa.String(60), nullable=False),
        sa.Column("fn", sa.String(120), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.create_index("ix_job_runs_job", "job_runs", ["job"])
    op.create_index("ix_job_runs_started_at", "job_runs", ["started_at"])


def downgrade() -> None:
    op.drop_table("job_runs")
    op.drop_table("request_counters")
    op.drop_table("request_logs")
