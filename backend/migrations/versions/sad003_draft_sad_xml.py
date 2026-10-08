"""Draft SAD: XML z WinSAD dołączony do wersji draftu (dosyłany po PDF).

Revision ID: sad003
Revises: sad002
"""
import sqlalchemy as sa
from alembic import op

revision = "sad003"
down_revision = "sad002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sad_drafts") as batch:
        batch.add_column(sa.Column("xml_attachment_id", sa.Integer, nullable=True))
        batch.add_column(sa.Column("xml_sha256", sa.String(64), nullable=True))
        batch.create_foreign_key("fk_sad_drafts_xml_attachment", "attachments",
                                 ["xml_attachment_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("sad_drafts") as batch:
        batch.drop_constraint("fk_sad_drafts_xml_attachment", type_="foreignkey")
        batch.drop_column("xml_sha256")
        batch.drop_column("xml_attachment_id")
