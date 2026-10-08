"""Jednorazowy reset users.ui_prefs — czyszczenie skażenia między kontami.

Przed fixem izolacji (PR #319) pullPrefs nie czyścił localStorage poprzedniego
usera, a push wysyłał cały syncowalny stan — profile widoku mogły zawierać
cudze zapisane widoki/kolumny. Zerujemy wszystkim; każdy zaczyna z czystym
profilem (fix gwarantuje, że skażenie już nie wróci).

Revision ID: b7e1a9c3d5f2
Revises: 0c10984de306
"""
import sqlalchemy as sa
from alembic import op

revision = "b7e1a9c3d5f2"
down_revision = "0c10984de306"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE users SET ui_prefs = ''"))


def downgrade() -> None:
    pass  # danych sprzed resetu nie da się odtworzyć — świadomie no-op
