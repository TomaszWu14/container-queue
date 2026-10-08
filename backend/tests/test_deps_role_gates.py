"""Bramki ról tylko w deps.py (audyt 2026-09-23, P6): brak bramek w treści handlerów
i brak redefinicji krotek require_roles, które deps już ma."""
import pathlib
import re

import pytest
from fastapi import HTTPException

from app.deps import READER_ROLES, CommercialReaders, NonWarehouseViewers
from app.models import Role, User

ROUTERS = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers"

# `if user.role == Role.warehouse: raise 403` / `in (Role.warehouse, Role.customs)` w handlerze
_INLINE_GATE = re.compile(
    r"if user\.role (?:== Role\.warehouse|in \(Role\.warehouse, Role\.customs\)):[^\n]*\n"
    r"\s+raise HTTPException\(status\.HTTP_403_FORBIDDEN")
# krotki identyczne z deps.Editors / AdminOnly / PurchasingReaders
_REDEFINED = re.compile(
    r"Depends\(require_roles\((?:Role\.admin|Role\.admin, Role\.logistics"
    r"|Role\.admin, Role\.logistics, Role\.purchasing)\)\)")


def _offenders(pattern):
    return [p.name for p in ROUTERS.glob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]


def test_no_inline_warehouse_customs_gates_in_routers():
    assert _offenders(_INLINE_GATE) == [], "użyj deps.NonWarehouseViewers / CommercialReaders"


def test_no_redefined_deps_role_tuples_in_routers():
    assert _offenders(_REDEFINED) == [], "importuj Editors / AdminOnly / PurchasingReaders z deps"


@pytest.mark.parametrize("gate, denied", [
    (NonWarehouseViewers, {Role.warehouse}),
    (CommercialReaders, {Role.warehouse, Role.customs}),
])
def test_gate_allows_readers_minus_denied(gate, denied):
    checker = gate.dependency
    for role in Role:
        user = User(login="x", hashed_password="x", role=role)
        if role in READER_ROLES and role not in denied:
            assert checker(user) is user
        else:   # fail-closed: nowa rola spoza READER_ROLES też nie przechodzi
            with pytest.raises(HTTPException) as exc:
                checker(user)
            assert exc.value.status_code == 403
