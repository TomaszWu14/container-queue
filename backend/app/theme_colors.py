"""Kolory motywów ustawiane przez admina (Administracja → Kolory) — nadpisania tokenów CSS dla
motywu jasnego i ciemnego, wspólne dla wszystkich użytkowników. Trzymane w AppSetting jako JSON;
brak wpisu = kolory domyślne z 00-tokens.css. Wartości to wyłącznie #rrggbb, a klucze nazwy
tokenów `--…`, więc front może je bezpiecznie wstawić przez style.setProperty (bez wstrzyknięcia CSS)."""
import json
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from .database import get_db
from .deps import AdminOnly as admin_only
from .models import AppSetting, User
from .security import get_current_user

KEY = "theme_colors"
MODES = ("light", "dark")
MAX_TOKENS = 60                                  # na motyw — z zapasem ponad edytowalną listę frontu
_TOKEN = re.compile(r"^--[a-z0-9][a-z0-9-]{1,40}$")
_HEX = re.compile(r"^#[0-9a-f]{6}$")


class ThemeColors(BaseModel):
    light: dict[str, str] = {}
    dark: dict[str, str] = {}

    @field_validator("light", "dark")
    @classmethod
    def _tokens(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > MAX_TOKENS:
            raise ValueError(f"Najwyżej {MAX_TOKENS} kolorów na motyw.")
        out = {}
        for token, color in v.items():
            color = color.strip().lower()
            if not _TOKEN.match(token) or not _HEX.match(color):
                raise ValueError(f"Nieprawidłowy kolor {token}: {color!r} (oczekiwany #rrggbb).")
            out[token] = color
        return dict(sorted(out.items()))


def load(db: Session) -> ThemeColors:
    row = db.get(AppSetting, KEY)
    try:
        return ThemeColors(**json.loads(row.value)) if row and row.value else ThemeColors()
    except ValueError:   # uszkodzony wpis → kolory domyślne zamiast 500 na każdej stronie
        return ThemeColors()


router = APIRouter(prefix="/api", tags=["administracja"])


@router.get("/theme-colors", response_model=ThemeColors)
def get_theme_colors(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Każdy zalogowany — kolory obowiązują wszystkich, niezależnie od roli."""
    return load(db)


@router.put("/admin/theme-colors", response_model=ThemeColors)
def put_theme_colors(body: ThemeColors, db: Session = Depends(get_db), user: User = admin_only):
    from .audit import record
    old = load(db)
    for mode in MODES:
        before, after = getattr(old, mode), getattr(body, mode)
        changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
        if changed:
            record(db, entity_type="settings", entity_id=0, field=f"theme_colors_{mode}",
                   old_value=f"{len(before)} nadpisań", new_value=f"{len(after)} nadpisań", user=user,
                   note=f"kolory motywu {'jasnego' if mode == 'light' else 'ciemnego'}: {', '.join(changed)}"[:500])
    row = db.get(AppSetting, KEY)
    value = body.model_dump_json()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=KEY, value=value))
    db.commit()
    return load(db)
