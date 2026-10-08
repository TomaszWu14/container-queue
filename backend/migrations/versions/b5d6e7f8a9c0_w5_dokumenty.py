"""W5 dokumenty: propozycje podpięcia z OCR + szablony wysyłki do agencji

Revision ID: b5d6e7f8a9c0
Revises: e8f9a0b1c2d4
"""
import sqlalchemy as sa
from alembic import op

revision = "b5d6e7f8a9c0"
down_revision = "e8f9a0b1c2d4"
branch_labels = None
depends_on = None

suggestion_status = sa.Enum("proposed", "accepted", "rejected", name="suggestionstatus")


def upgrade() -> None:
    op.create_table(
        "attachment_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("invoice_jobs.id"), nullable=False),
        sa.Column("container_id", sa.Integer(), sa.ForeignKey("containers.id"), nullable=False),
        sa.Column("doc_kind", sa.String(20), nullable=False, server_default=""),
        sa.Column("status", suggestion_status, nullable=False, server_default="proposed"),
        sa.Column("document_type_id", sa.Integer(), sa.ForeignKey("document_types.id"),
                  nullable=True),
        sa.Column("attachment_id", sa.Integer(), sa.ForeignKey("attachments.id"),
                  nullable=True),
        sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_attachment_suggestions_job_id", "attachment_suggestions", ["job_id"])
    op.create_index("ix_attachment_suggestions_container_id", "attachment_suggestions",
                    ["container_id"])
    op.create_index("ix_attachment_suggestions_status", "attachment_suggestions", ["status"])
    op.create_table(
        "doc_send_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customs_agency_id", sa.Integer(), sa.ForeignKey("customs_agencies.id"),
                  nullable=True),
        sa.Column("subject", sa.String(200), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_doc_send_templates_customs_agency_id", "doc_send_templates",
                    ["customs_agency_id"])


def downgrade() -> None:
    op.drop_table("doc_send_templates")
    op.drop_table("attachment_suggestions")
    suggestion_status.drop(op.get_bind(), checkfirst=True)
