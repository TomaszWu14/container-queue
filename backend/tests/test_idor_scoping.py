"""IDOR poza kontenerami (audyt N-24: ACL-004, TEST-004).

test_idor_containers pilnuje tras z {container_id}; tu — pozostałe trasy z id zasobu
należącego do spółki/kontenera/spedytora (zlecenia, reklamacje, zdjęcia, faktury, awizacje…).
Świat B (inna spółka, spedytor, agencja, magazyn) ma po jednym rekordzie każdego typu;
konta spółki A (każda rola poza adminem) wołają trasy z id świata B → nigdy 2xx.
Kontrola pozytywna: admin (widzi wszystko) GET-em na te same id → nie 404, czyli rekordy
świata B są realne i test sprawdza zakres, a nie brak danych.
Słowniki globalne (porty, spedytorzy, przewoźnicy, materiały, baza wiedzy…) — poza zakresem
(ACL-003/ACL-006); trasy z id spoza PARAM nie są sprawdzane.
"""
import datetime

import pytest
import sqlalchemy as sa
import yaml
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.deps import get_scoped
from app.main import app
from app.models.enums import Role
from app.security import create_access_token
from tests.test_idor_containers import _body, _sample
from tests.test_permissions_matrix import YAML_PATH, _fill, _routes

ROLES = [r.value for r in Role if r != Role.admin]  # admin widzi wszystko
MODELS = {m.class_.__tablename__: m.class_ for m in Base.registry.mappers}

# parametr ścieżki → tabela rekordu świata B (po fragmencie ścieżki, gdy nazwa niejednoznaczna)
PARAM = {
    "attachment_id": "attachments", "batch_id": "invoice_batches", "call_id": "pallet_calls",
    "complaint_id": "complaints", "invoice_id": "freight_invoices", "link_id": "sent_links",
    "po_id": "purchase_orders", "request_id": "avizo_requests", "customer_id": "customers",
    "proposal_id": "avizo_change_proposals", "suggestion_id": "attachment_suggestions",
    "supplier_id": "suppliers", "alias_id": "supplier_aliases", "session_id": "refresh_tokens",
    "map_id": "supplier_material_maps", "quote_id": "quotes", "user_id": "users",
    "warehouse_id": "warehouses", "company_id": "companies", "entity_id": "purchase_orders",
}
BY_PATH = {
    ("job_id", "/invoice-jobs/"): "invoice_jobs", ("job_id", "/transport-jobs/"): "transport_jobs",
    ("order_id", "/customer-orders/"): "customer_orders", ("order_id", "/orders/"): "orders",
    ("order_id", "/transport-orders/"): "transport_orders",
    ("photo_id", "/complaint-photos/"): "complaint_photos",
    ("photo_id", "/unload-photos/"): "unload_photos",
    ("batch_id", "/intake/"): "intake_batches", ("item_id", "/intake/items/"): "intake_items",
}

# świadome 404 dla braku pliku (nie brak dostępu) — kontrola pozytywna ich nie wymaga
EMPTY_IS_404 = {
    "GET /api/freight-invoices/{invoice_id}/download",
    "GET /api/invoice-batches/{batch_id}/sad-drafts/{draft_id}/pages/{page}",  # draft 999999
    "GET /api/suppliers/{supplier_id}/doc-profile/samples/{sample_id}/preview",
    "GET /api/users/{user_id}/avatar",
    "GET /api/intake/items/{item_id}/file",   # atrapa bez pliku części
}

# Znane dziury (xfail strict): trasa → powód. Osobny PR z poprawką usuwa wpis.
KNOWN = {}


def _query(r) -> dict:
    """Wymagane parametry query (np. ?stage=) — inaczej 422 przed kontrolą zakresu."""
    return {q.alias: _sample(q.field_info.annotation) for q in r.dependant.query_params
            if q.field_info.is_required()}


# pola z walidatorami formatu (e-mail, telefon, tablice) — poprawna wartość, żeby żądanie
# doszło do kontroli zakresu, także w zagnieżdżonych pozycjach (formularz kierowców)
_VALID = {"driver_phone": "+48600100200", "truck_no": "WGM1234A", "trailer_no": ""}


def _fix(value):
    if isinstance(value, list):
        return [_fix(v) for v in value]
    if isinstance(value, dict):
        return {k: "idor@example.com" if "email" in k else _VALID.get(k, _fix(v))
                for k, v in value.items()}
    return value


def _kwargs(r) -> dict:
    """_body z test_idor_containers + poprawne wartości pól z walidatorami formatu."""
    kw = _body(r)
    if isinstance(kw.get("json"), dict):
        kw["json"] = _fix(kw["json"])
    return kw


def _table(name, path):
    # BY_PATH najpierw: batch_id w /intake/ to wgranie poczekalni, nie paczka faktur
    return next((t for (n, frag), t in BY_PATH.items() if n == name and frag in path),
                None) or PARAM.get(name)


def _scoped_routes():
    for key, (m, p, r) in sorted(_routes().items()):
        names = {q.name for q in r.dependant.path_params}
        if "/public/" in p or names & {"container_id", "cid"}:  # portal / test_idor_containers
            continue
        if any(_table(n, p) for n in names):
            yield key, m, p, r


def _url(p, r, ids):
    for q in r.dependant.path_params:
        table = _table(q.name, p)
        if table:
            p = p.replace(f"{{{q.name}}}", str(ids[table]))
    return _fill(p.replace("{entity_type}", "purchase_orders"), r)


_n = iter(range(1, 10**6))


def _mk(db, table, **kw):
    """Rekord z uzupełnionymi kolumnami wymaganymi (bez domyślnych) — FK podaje wołający."""
    model = MODELS[table]
    for c in model.__table__.columns:
        if c.name in kw or c.nullable or c.primary_key or c.foreign_keys \
                or c.default is not None or c.server_default is not None:
            continue
        ty = c.type
        if isinstance(ty, sa.Enum):
            kw[c.name] = list(ty.enum_class)[0] if ty.enum_class else ty.enums[0]
        elif isinstance(ty, sa.DateTime):
            kw[c.name] = datetime.datetime(2030, 1, 1)
        elif isinstance(ty, sa.Date):
            kw[c.name] = datetime.date(2030, 1, 1)
        elif isinstance(ty, (sa.Integer, sa.Float, sa.Numeric)):
            kw[c.name] = 1
        else:
            kw[c.name] = f"IDOR{next(_n)}"[: getattr(ty, "length", None) or 40]
    obj = model(**kw)
    db.add(obj)
    db.flush()
    return obj


def _side(db, tag):
    """Komplet zasobów jednej strony; zwraca ({tabela: id}, organizacja strony)."""
    co = _mk(db, "companies", name=f"IDOR2 {tag}", code=f"IS{tag}")
    fwd = _mk(db, "forwarders", name=f"IDOR2 FWD {tag}")
    ag = _mk(db, "customs_agencies", name=f"IDOR2 AG {tag}")
    wh = _mk(db, "warehouses", company_id=co.id)
    box = _mk(db, "containers", container_no=f"ISOU000000{1 if tag == 'A' else 2}",
              company_id=co.id, forwarder_id=fwd.id, customs_agency_id=ag.id, warehouse_id=wh.id)
    c, own = co.id, {"company_id": co.id}
    user = _mk(db, "users", login=f"idor2_owner_{tag}", role=Role.logistics, **own)
    batch = _mk(db, "invoice_batches", container_id=box.id)
    job = _mk(db, "invoice_jobs", batch_id=batch.id)
    intake = _mk(db, "intake_batches", container_id=box.id)
    complaint = _mk(db, "complaints", container_id=box.id, **own)
    tjob = _mk(db, "transport_jobs")
    _mk(db, "transport_job_containers", job_id=tjob.id, container_id=box.id)
    supplier = _mk(db, "suppliers", client_company_id=c)
    avizo = _mk(db, "avizo_requests", forwarder_id=fwd.id, **own)
    rows = {
        "attachments": _mk(db, "attachments", container_id=box.id),
        "attachment_suggestions": _mk(db, "attachment_suggestions", job_id=job.id,
                                      container_id=box.id),
        "pallet_calls": _mk(db, "pallet_calls", **own),
        "complaint_photos": _mk(db, "complaint_photos", complaint_id=complaint.id),
        "freight_invoices": _mk(db, "freight_invoices", forwarder_id=fwd.id, **own),
        "quotes": _mk(db, "quotes", job_id=tjob.id, forwarder_id=fwd.id),
        "sent_links": _mk(db, "sent_links", **own),
        "orders": _mk(db, "orders", **own),
        "customer_orders": _mk(db, "customer_orders", **own),
        "customers": _mk(db, "customers", **own),
        "transport_orders": _mk(db, "transport_orders", container_id=box.id,
                                forwarder_id=fwd.id, **own),
        "unload_photos": _mk(db, "unload_photos", container_id=box.id),
        "purchase_orders": _mk(db, "purchase_orders", **own),
        "avizo_change_proposals": _mk(db, "avizo_change_proposals", request_id=avizo.id,
                                      container_id=box.id),
        "supplier_aliases": _mk(db, "supplier_aliases", supplier_id=supplier.id, **own),
        "supplier_material_maps": _mk(db, "supplier_material_maps", supplier_id=supplier.id,
                                      **own),
        "refresh_tokens": _mk(db, "refresh_tokens", user_id=user.id),
        "intake_items": _mk(db, "intake_items", batch_id=intake.id),
    }
    ids = {t: o.id for t, o in rows.items()}
    ids.update(companies=c, warehouses=wh.id, containers=box.id, users=user.id,
               invoice_batches=batch.id, invoice_jobs=job.id, intake_batches=intake.id, complaints=complaint.id,
               transport_jobs=tjob.id, suppliers=supplier.id, avizo_requests=avizo.id)
    return ids, (co, fwd, ag, wh)


@pytest.fixture(scope="module")
def world(_db_template):
    engine.dispose()
    with engine.raw_connection() as raw:
        _db_template.backup(raw.driver_connection)
    db = SessionLocal()
    _, (co, fwd, ag, wh) = _side(db, "A")
    foreign, _ = _side(db, "B")
    tokens = {}
    for role in ROLES:
        u = _mk(db, "users", login=f"idor2_{role}", role=Role(role), company_id=co.id,
                forwarder_id=fwd.id, customs_agency_id=ag.id, warehouse_id=wh.id)
        tokens[role] = {"Authorization": f"Bearer {create_access_token(u)}"}
    admin = db.scalar(sa.select(MODELS["users"]).where(MODELS["users"].role == Role.admin))
    tokens["admin"] = {"Authorization": f"Bearer {create_access_token(admin)}"}
    db.commit()
    db.close()
    matrix = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))["routes"]
    # SMTP „skonfigurowany” — inaczej guard 422 przed get_*_checked zasłania zakres (wysyłki)
    with pytest.MonkeyPatch.context() as mp, TestClient(app) as client:
        mp.setattr(settings, "smtp_host", "smtp.test.local")
        yield client, tokens, foreign, matrix


def _cases():
    for key, m, p, r in _scoped_routes():
        marks = [pytest.mark.xfail(strict=True, reason=KNOWN[key])] if key in KNOWN else []
        yield pytest.param(key, m, p, r, id=key, marks=marks)


@pytest.mark.parametrize("key,m,p,r", list(_cases()))
def test_foreign_resource_never_2xx(world, key, m, p, r):
    client, tokens, foreign, matrix = world
    leaks, unsure = [], []
    for role in ROLES:
        if matrix[key][role] == 403:
            continue  # rola i tak odrzucona — pilnuje test_permissions_matrix
        got = client.request(m, _url(p, r, foreign), headers=tokens[role],
                             params=_query(r), **_kwargs(r))
        if 200 <= got.status_code < 300:
            leaks.append(f"[{role}] → {got.status_code}")
        elif got.status_code == 422:
            unsure.append(f"[{role}] {got.text[:120]}")
    assert not leaks, f"IDOR {key} — zasób świata B dostępny: {leaks}"
    assert not unsure, f"{key}: 422 zasłania kontrolę zakresu (uzupełnij _sample): {unsure}"


def test_foreign_records_exist_for_admin(world):
    """Kontrola pozytywna — bez niej „wszędzie 404” przeszłoby jako sukces."""
    client, tokens, foreign, _ = world
    hidden = [f"{key} → {got}" for key, m, p, r in _scoped_routes() if m == "GET"
              and (got := client.get(_url(p, r, foreign), headers=tokens["admin"]).status_code)
              == 404 and key not in EMPTY_IS_404]
    assert not hidden, "Rekord świata B niewidoczny nawet dla admina:\n" + "\n".join(hidden)


def test_refresh_token_is_not_access_token(client):
    """TEST-004: refresh użyty jako Bearer → 401 (security.get_current_user, typ tokenu)."""
    tokens = client.post("/api/auth/login",
                         data={"username": "admin", "password": "admin123"}).json()
    got = client.get("/api/auth/me",
                     headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert got.status_code == 401


def test_inactive_user_token_rejected(client, db_session):
    """TEST-004: token wystawiony przed dezaktywacją konta → 401."""
    user = _mk(db_session, "users", login="idor2_inactive", role=Role.logistics)
    hdr = {"Authorization": f"Bearer {create_access_token(user)}"}
    db_session.commit()
    assert client.get("/api/auth/me", headers=hdr).status_code == 200
    user.is_active = False
    db_session.commit()
    assert client.get("/api/auth/me", headers=hdr).status_code == 401


def test_enforce_scope_fail_closed(client, db_session):
    """TEST-004: zasób bez znanej reguły izolacji → 403 (deps._enforce_scope, fail-closed)."""
    fwd = _mk(db_session, "forwarders", name="IDOR2 bez reguły")
    user = _mk(db_session, "users", login="idor2_fail_closed", role=Role.logistics)
    with pytest.raises(HTTPException) as exc:
        get_scoped(db_session, MODELS["forwarders"], fwd.id, user)
    assert exc.value.status_code == 403
