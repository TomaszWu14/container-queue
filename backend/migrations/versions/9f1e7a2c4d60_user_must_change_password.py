"""users.must_change_password — wymuszenie zmiany hasła przy pierwszym logowaniu

Revision ID: 9f1e7a2c4d60
Revises: c7d8e9f0a1b2
Create Date: 2026-07-17

Konta zakładane z zaproszenia dostają hasło tymczasowe i flagę must_change_password;
po pierwszym zalogowaniu użytkownik musi ustawić własne hasło.
"""
import sqlalchemy as sa
from alembic import op

revision = '9f1e7a2c4d60'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default=false: istniejące konta nie wymuszają zmiany hasła.
    op.add_column('users', sa.Column('must_change_password',
                                     sa.Boolean(create_constraint=False),
                                     nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('users', 'must_change_password')
