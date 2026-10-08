"""Macierz uprawnień: rola × trasa × metoda porównana z tests/permissions.yaml (repo root).

1. Statycznie: role wpuszczane przez zależności (require_roles) == YAML.
   Nowa trasa bez wpisu / wpis po usuniętej trasie / zmiana ról bez aktualizacji YAML = błąd.
   Szkic YAML dla nowych tras: `python ../tests/gen_permissions.py` (z katalogu backend/).
2. Na żywo: każda komórka 403 → faktycznie 403, anon → 401 (odrzucenie w zależności, przed
   kodem handlera — żadnych skutków ubocznych), komórki rozstrzygane w treści handlera
   (w YAML z komentarzem „rola sprawdzana też w treści”) → zgodne z YAML.
"""
import pathlib
import re

import pytest
import yaml
from fastapi.testclient import TestClient

from app.database import SessionLocal, engine
from app.main import app
from app.models import Company, CustomsAgency, Forwarder, User, Warehouse
from app.models.enums import Role
from app.security import create_access_token, get_current_user
from tests.test_routes_require_auth import PUBLIC, _api_routes

YAML_PATH = pathlib.Path(__file__).resolve().parents[2] / "tests" / "permissions.yaml"
ROLES = [r.value for r in Role]
OK = {"GET": 200, "POST": "2xx", "PUT": 200, "PATCH": 200, "DELETE": "2xx"}


def _deps(dependant):
    for d in dependant.dependencies:
        yield d
        yield from _deps(d)


def _body_roles(route) -> set[str]:
    import inspect
    try:
        return set(re.findall(r"Role\.(\w+)", inspect.getsource(route.endpoint)))
    except (OSError, TypeError):
        return set()


def derive(method: str, path: str, route) -> dict:
    """Oczekiwany wynik per rola wynikający z drzewa zależności trasy."""
    if (method, path) in PUBLIC:
        return {"anon": "public"}
    allowed = set(ROLES)
    global_data = False
    for d in _deps(route.dependant):
        cells = getattr(d.call, "__closure__", None) or ()
        if getattr(d.call, "__name__", "") == "checker":  # require_roles(...)
            roles = {v.value for c in cells if isinstance(c.cell_contents, tuple)
                     for v in c.cell_contents if isinstance(v, Role)}
            if roles:
                allowed &= roles
        if getattr(d.call, "__name__", "") == "_global_data_editor":
            global_data = True   # ACL-003: logistyka zależnie od spółki/view_all
    body = _body_roles(route)
    out = {"anon": 401}
    for r in ROLES:
        out[r] = OK[method] if r in allowed else 403
        if r in body and body != allowed:
            out[r] = "?"  # rozstrzyga handler — wartość w YAML ustala test na żywo
    if global_data and "logistics" in allowed:
        out["logistics"] = "?"   # konto matrycy = logistyka jednej spółki → YAML 403 (na żywo)
    return out


@pytest.fixture(scope="module")
def matrix():
    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))["routes"]


def _routes():
    return {f"{m} {p}": (m, p, r) for m, p, r in _api_routes()}


def test_yaml_covers_exactly_current_routes(matrix):
    current = set(_routes())
    missing, stale = sorted(current - set(matrix)), sorted(set(matrix) - current)
    assert not missing and not stale, (
        f"Brak w permissions.yaml (dopisz; szkic: gen_permissions.py): {missing}\n"
        f"Nieistniejące trasy w permissions.yaml (usuń): {stale}")


def test_yaml_matches_route_dependencies(matrix):
    diffs = []
    for key, (m, p, r) in _routes().items():
        want = derive(m, p, r)
        for role, val in want.items():
            if val != "?" and matrix.get(key, {}).get(role) != val:
                diffs.append(f"{key} [{role}]: kod={val} yaml={matrix.get(key, {}).get(role)}")
    assert not diffs, "Zależności tras ≠ permissions.yaml (świadomie zaktualizuj YAML):\n" + \
        "\n".join(diffs)


# --- na żywo -------------------------------------------------------------------------

def _fill(path: str, route) -> str:
    for p in route.dependant.path_params:
        ann = getattr(p, "type_", None) or getattr(p.field_info, "annotation", str)
        path = path.replace("{%s}" % p.name, "999999" if ann is int else "x")
    return re.sub(r"\{[^}]+\}", "x", path)


@pytest.fixture(scope="module")
def live(_db_template):
    """Jeden klient i komplet kont (po jednym na rolę, spółka A) na cały moduł.
    Partnerzy (spedytor, agencja) jak na produkcji — BEZ spółki: zakres wg forwarder_id /
    customs_agency_id. Wariant ze spółką (stare dane) pilnuje test_partner_company_scope."""
    engine.dispose()
    with engine.raw_connection() as raw:
        _db_template.backup(raw.driver_connection)
    db = SessionLocal()
    company = db.query(Company).order_by(Company.id).first()
    fwd = db.query(Forwarder).order_by(Forwarder.id).first() or Forwarder(name="Matrix FWD")
    agency = CustomsAgency(name="Matrix Agencja")
    wh = db.query(Warehouse).order_by(Warehouse.id).first()
    db.add_all([fwd, agency])
    db.flush()
    links = {"forwarder": {"forwarder_id": fwd.id}, "customs": {"customs_agency_id": agency.id},
             "warehouse": {"warehouse_id": wh.id if wh else None}}
    tokens = {}
    for role in ROLES:
        u = User(login=f"matrix_{role}", hashed_password="x", role=Role(role),
                 company_id=None if role in ("forwarder", "customs") else company.id,
                 **links.get(role, {}))
        db.add(u)
        db.flush()
        tokens[role] = {"Authorization": f"Bearer {create_access_token(u)}"}
    db.commit()
    db.close()
    with TestClient(app) as client:
        yield client, tokens


def test_denied_cells_return_403_and_anon_401(live, matrix):
    client, tokens = live
    wrong = []
    for key, (m, p, r) in _routes().items():
        cells = matrix[key]
        if cells.get("anon") == "public":
            continue
        url = _fill(p, r)
        got = client.request(m, url).status_code
        if got != 401:
            wrong.append(f"{key} [anon]: {got} ≠ 401")
        for role in ROLES:
            if cells[role] == 403:
                got = client.request(m, url, headers=tokens[role]).status_code
                if got != 403:
                    wrong.append(f"{key} [{role}]: {got} ≠ 403")
    assert not wrong, "Macierz uprawnień złamana:\n" + "\n".join(wrong)


def test_handler_checked_cells_match_yaml(live, matrix):
    """Komórki, które rozstrzyga kod handlera (derive → '?'); YAML trzyma zaobserwowany wynik."""
    client, tokens = live
    wrong = []
    for key, (m, p, r) in _routes().items():
        want = derive(m, p, r)
        for role in ROLES:
            if want.get(role) != "?":
                continue
            got = client.request(m, _fill(p, r), headers=tokens[role]).status_code
            exp = matrix[key][role]
            ok = got == 403 if exp == 403 else got not in (401, 403)
            if not ok:
                wrong.append(f"{key} [{role}]: {got}, yaml={exp}")
    assert not wrong, "Uprawnienia sprawdzane w handlerze ≠ permissions.yaml:\n" + "\n".join(wrong)


def test_get_current_user_is_the_auth_root():
    # bezpiecznik: gdyby auth przeniesiono do innej funkcji, derive() i strażnik PUBLIC
    # przestałyby cokolwiek sprawdzać
    assert any(d.call is get_current_user for m, p, r in _api_routes()
               for d in _deps(r.dependant))
