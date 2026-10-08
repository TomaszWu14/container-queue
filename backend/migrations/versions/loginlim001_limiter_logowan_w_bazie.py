"""ARCH-003 + SEC-012: stan limitera logowań w bazie (tabela login_failures).

Wcześniej słownik w pamięci procesu (rate_limit.LoginRateLimiter): deploy zerował liczniki,
a każdy worker / instancja liczył osobno (limit ×N). Wiersz = jedna porażka dla klucza
limitera; `key` to SHA-256 klucza (bez jawnego IP i wpisanego loginu). Tabela startuje
pusta — liczniki sprzed wdrożenia (w pamięci) i tak ginęły przy każdym restarcie, więc
nic nie przenosimy; dane produkcyjne nie są dotykane.

Revision ID: loginlim001
Revises: fkidx001
"""
import sqlalchemy as sa
from alembic import op

revision = "loginlim001"
down_revision = "fkidx001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_failures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        if_not_exists=True,   # dev/SQLite: bootstrap create_all mógł ją już założyć
    )
    op.create_index("ix_login_failures_key_created", "login_failures", ["key", "created_at"],
                    if_not_exists=True)
    op.create_index("ix_login_failures_created_at", "login_failures", ["created_at"],
                    if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_login_failures_created_at", table_name="login_failures", if_exists=True)
    op.drop_index("ix_login_failures_key_created", table_name="login_failures", if_exists=True)
    op.drop_table("login_failures", if_exists=True)
