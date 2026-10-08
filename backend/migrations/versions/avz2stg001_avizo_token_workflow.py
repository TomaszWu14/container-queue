"""awizacja dwuetapowa: statusy, jednorazowe tokeny, odpowiedzi etapu 1, log maili

Revision ID: avz2stg001
Revises: sl1slot001
Create Date: 2026-09-23
"""
import sqlalchemy as sa
from alembic import op

revision = "avz2stg001"
down_revision = "sl1slot001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("avizo_requests", sa.Column("status", sa.String(30), nullable=False,
                                              server_default="SENT_STAGE1"))
    op.create_index("ix_avizo_requests_status", "avizo_requests", ["status"])
    op.add_column("avizo_requests", sa.Column("language", sa.String(2), nullable=False,
                                              server_default="pl"))
    op.add_column("avizo_requests", sa.Column("reject_comment", sa.Text(), nullable=False,
                                              server_default=""))
    op.add_column("avizo_requests", sa.Column("approved_by_id", sa.Integer(), nullable=True))
    op.add_column("avizo_requests", sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.add_column("avizo_requests", sa.Column("closed_at", sa.DateTime(), nullable=True))
    op.add_column("avizo_requests", sa.Column("driver_data_purged_at", sa.DateTime(),
                                              nullable=True))
    op.add_column("forwarders", sa.Column("language", sa.String(2), nullable=False,
                                          server_default="pl"))
    op.add_column("companies", sa.Column("avizo_cc", sa.String(500), nullable=False,
                                         server_default=""))

    op.create_table(
        "avizo_form_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("avizo_requests.id"), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_avizo_form_tokens_request_id", "avizo_form_tokens", ["request_id"])
    op.create_index("ix_avizo_form_tokens_token_hash", "avizo_form_tokens", ["token_hash"],
                    unique=True)
    op.create_table(
        "avizo_delivery_confirmations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("avizo_requests.id"), nullable=False),
        sa.Column("container_id", sa.Integer(), sa.ForeignKey("containers.id"), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("proposed_date", sa.Date(), nullable=True),
        sa.Column("proposed_time", sa.String(5), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("submit_ip", sa.String(64), nullable=False),
    )
    op.create_index("ix_avizo_delivery_confirmations_request_id",
                    "avizo_delivery_confirmations", ["request_id"])
    op.create_index("ix_avizo_delivery_confirmations_container_id",
                    "avizo_delivery_confirmations", ["container_id"])
    op.create_table(
        "avizo_mail_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("avizo_requests.id"), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("recipients", sa.Text(), nullable=False),
        sa.Column("cc", sa.Text(), nullable=False),
        sa.Column("backend", sa.String(20), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_avizo_mail_logs_request_id", "avizo_mail_logs", ["request_id"])

    # istniejące zlecenia: stare linki przechodzą na AvizoFormToken(stage=1) z tym samym
    # hashem i ważnością; potwierdzone = token zużyty + status CONFIRMED_BY_FORWARDER
    op.execute(
        "INSERT INTO avizo_form_tokens (request_id, stage, token_hash, expires_at, used_at, "
        "created_at) SELECT id, 1, token, COALESCE(expires_at, created_at), confirmed_at, "
        "created_at FROM avizo_requests")
    op.execute("UPDATE avizo_requests SET status='CONFIRMED_BY_FORWARDER' "
               "WHERE confirmed_at IS NOT NULL")


def downgrade() -> None:
    op.drop_table("avizo_mail_logs")
    op.drop_table("avizo_delivery_confirmations")
    op.drop_table("avizo_form_tokens")
    op.drop_column("companies", "avizo_cc")
    op.drop_column("forwarders", "language")
    op.drop_index("ix_avizo_requests_status", table_name="avizo_requests")
    for col in ("driver_data_purged_at", "closed_at", "approved_at", "approved_by_id",
                "reject_comment", "language", "status"):
        op.drop_column("avizo_requests", col)
