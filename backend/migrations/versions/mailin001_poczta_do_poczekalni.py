"""Poczta → poczekalnia (spec 2026-10-06 decyzja 27): wgranie bez kontenera („poczta bez
dopasowania”), spółka wgrania, nadawca/temat i sha256 maila (ponowne wysłanie bez dubli).

Revision ID: mailin001
Revises: reqdoc001
"""
import sqlalchemy as sa
from alembic import op

revision = "mailin001"
down_revision = "reqdoc001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("intake_batches") as b:
        b.alter_column("container_id", existing_type=sa.Integer(), nullable=True)
        b.add_column(sa.Column("company_id", sa.Integer, nullable=True))
        b.add_column(sa.Column("note", sa.Text, nullable=True))
        b.add_column(sa.Column("mail_sha256", sa.String(64), nullable=True))
        b.create_foreign_key("fk_intake_batches_company_id", "companies", ["company_id"], ["id"])
        b.create_index("ix_intake_batches_company_id", ["company_id"])
        b.create_index("ix_intake_batches_mail_sha256", ["mail_sha256"])


def downgrade() -> None:
    op.execute("DELETE FROM intake_items WHERE batch_id IN "
               "(SELECT id FROM intake_batches WHERE container_id IS NULL)")
    op.execute("DELETE FROM intake_batches WHERE container_id IS NULL")
    with op.batch_alter_table("intake_batches") as b:
        b.drop_index("ix_intake_batches_mail_sha256")
        b.drop_index("ix_intake_batches_company_id")
        b.drop_constraint("fk_intake_batches_company_id", type_="foreignkey")
        b.drop_column("mail_sha256")
        b.drop_column("note")
        b.drop_column("company_id")
        b.alter_column("container_id", existing_type=sa.Integer(), nullable=False)
