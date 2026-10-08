"""deps.scope_company — jedno miejsce filtra spółki dla list (audyt 2026-09-23, P3)."""
import pathlib
import re

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.deps import scope_company
from app.models import PalletCall, Role, User


def _sql(q) -> str:
    return str(q.compile(compile_kwargs={"literal_binds": True}))


def test_view_all_user_query_unchanged():
    q = select(PalletCall)
    admin = User(login="a", hashed_password="x", role=Role.admin)
    assert _sql(scope_company(q, PalletCall.company_id, admin)) == _sql(q)


def test_company_user_filtered_to_own_company():
    user = User(login="l", hashed_password="x", role=Role.logistics,
                view_all_companies=False, company_id=7)
    sql = _sql(scope_company(select(PalletCall), PalletCall.company_id, user))
    assert "pallet_calls.company_id IN (7)" in sql


def test_account_without_company_is_denied():
    user = User(login="l", hashed_password="x", role=Role.logistics,
                view_all_companies=False, company_id=None)
    with pytest.raises(HTTPException) as exc:
        scope_company(select(PalletCall), PalletCall.company_id, user)
    assert exc.value.status_code == 403


# ręczna kopia scope_company: ids = company_filter_ids(user); if ids is not None: q = q.where(X.in_(ids))
_COPY = re.compile(r"(\w+) = company_filter_ids\(user\)\n\s+if \1 is not None:\n"
                   r"\s+(\w+) = \2\.where\([\w.]+\.in_\(\1\)\)")


def test_routers_do_not_paste_scope_company():
    app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = [str(p.relative_to(app_dir)) for p in app_dir.rglob("*.py")
                 if p.name != "deps.py" and _COPY.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], f"użyj deps.scope_company zamiast kopii w: {offenders}"
