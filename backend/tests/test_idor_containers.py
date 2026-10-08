"""IDOR na kontenerach: każda trasa z {container_id}/{cid}, każda rola bez „widzę wszystko”.

Konto spółki A podmienia ID w URL na kontener OBCY we wszystkich wymiarach zakresu
(inna spółka, inny spedytor, inna agencja, inny magazyn) → nigdy 2xx.
Kontrola pozytywna: GET na WŁASNY kontener → nie 404/403 (inaczej test niczego nie dowodzi).
Zapisy dostają minimalnie poprawne body (_body) — inaczej 422 z walidacji zasłoniłby kontrolę
zakresu. 422 na obcym kontenerze = test niczego nie sprawdził → błąd testu (uzupełnij _sample).
"""
import datetime
import decimal
import enum
import types
import typing

import pytest
import yaml
from fastapi import UploadFile
from pydantic import BaseModel
from fastapi.testclient import TestClient

from app.database import SessionLocal, engine
from app.main import app
from app.models import Company, Container, CustomsAgency, Forwarder, User, Warehouse
from app.models.enums import Role
from app.security import create_access_token
from tests.test_permissions_matrix import YAML_PATH, _fill, _routes

ROLES = ["logistics", "warehouse", "forwarder", "customs", "purchasing"]  # admin widzi wszystko
PARAMS = ("container_id", "cid")


def _container_routes():
    for key, (m, p, r) in sorted(_routes().items()):
        names = {q.name for q in r.dependant.path_params}
        if names & set(PARAMS) and "/public/" not in p:  # portal: zakres = token
            yield key, m, p, r


def _url(p, r, container_id):
    for name in PARAMS:
        p = p.replace("{%s}" % name, str(container_id))
    return _fill(p, r)


def _sample(tp):
    """Minimalna wartość danego typu — żeby żądanie przeszło walidację i doszło do zakresu."""
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin in (typing.Union, types.UnionType):
        return _sample(next(a for a in args if a is not type(None)))
    if origin is typing.Literal:
        return args[0]
    if origin in (list, set, tuple):
        return []
    if origin is dict:
        return {}
    if isinstance(tp, type):
        if issubclass(tp, BaseModel):
            return {n: _field_sample(f) for n, f in tp.model_fields.items() if f.is_required()}
        if issubclass(tp, enum.Enum):
            return next(iter(tp)).value
        if issubclass(tp, bool):
            return False
        if issubclass(tp, (int, float, decimal.Decimal)):
            return 1
        if issubclass(tp, datetime.datetime):
            return "2026-01-15T10:00:00"
        if issubclass(tp, datetime.date):
            return "2026-01-15"
    return "IDOR test"


def _field_sample(field):
    """Lista z min_length ≥ 1 (np. pozycje formularza awizacji) — jeden przykładowy element,
    inaczej 422 zasłoniłby kontrolę zakresu."""
    tp = field.annotation
    if typing.get_origin(tp) is list and any(getattr(m, "min_length", 0) for m in field.metadata):
        return [_sample(typing.get_args(tp)[0])]
    return _sample(tp)


def _body(r) -> dict:
    """kwargs żądania: JSON z wymaganych pól albo multipart z małym plikiem."""
    params = r.dependant.body_params
    files = {b.name: ("a.pdf", b"%PDF-1.4 idor", "application/pdf") for b in params
             if typing.get_origin(b.field_info.annotation) is list
             or b.field_info.annotation is UploadFile}
    if files:
        return {"files": files}
    if len(params) == 1:
        return {"json": _sample(params[0].field_info.annotation)}
    return {}


@pytest.fixture(scope="module")
def world(_db_template):
    engine.dispose()
    with engine.raw_connection() as raw:
        _db_template.backup(raw.driver_connection)
    db = SessionLocal()

    def side(tag):
        co = Company(name=f"IDOR {tag}", code=f"ID{tag}")
        fwd, ag = Forwarder(name=f"IDOR FWD {tag}"), CustomsAgency(name=f"IDOR AG {tag}")
        db.add_all([co, fwd, ag])
        db.flush()
        wh = Warehouse(name=f"IDOR WH {tag}", company_id=co.id)
        db.add(wh)
        db.flush()
        box = Container(container_no=f"IDOU000000{1 if tag == 'A' else 2}", company_id=co.id,
                        forwarder_id=fwd.id, customs_agency_id=ag.id, warehouse_id=wh.id)
        db.add(box)
        db.flush()
        return co, fwd, ag, wh, box

    co, fwd, ag, wh, own = side("A")
    *_, foreign = side("B")
    tokens = {}
    for role in ROLES:
        u = User(login=f"idor_{role}", hashed_password="x", role=Role(role), company_id=co.id,
                 forwarder_id=fwd.id, customs_agency_id=ag.id, warehouse_id=wh.id)
        db.add(u)
        db.flush()
        tokens[role] = {"Authorization": f"Bearer {create_access_token(u)}"}
    ids = own.id, foreign.id
    db.commit()
    db.close()
    matrix = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))["routes"]
    with TestClient(app) as client:
        yield client, tokens, ids, matrix


def test_foreign_container_never_2xx(world):
    client, tokens, (_, foreign), matrix = world
    leaks, unsure = [], []
    for key, m, p, r in _container_routes():
        for role in ROLES:
            if matrix[key][role] == 403:
                continue  # rola i tak odrzucona — pilnuje test_permissions_matrix
            got = client.request(m, _url(p, r, foreign), headers=tokens[role],
                                 **_body(r)).status_code
            if 200 <= got < 300:
                leaks.append(f"{key} [{role}] → {got}")
            elif got == 422:
                unsure.append(f"{key} [{role}]")
    assert not leaks, "IDOR — obcy kontener dostępny:\n" + "\n".join(leaks)
    assert not unsure, "422 zasłania kontrolę zakresu (uzupełnij _sample):\n" + "\n".join(unsure)


def test_own_container_visible(world):
    """Kontrola pozytywna — bez niej „wszędzie 404” przeszłoby jako sukces."""
    client, tokens, (own, _), matrix = world
    hidden = []
    for key, m, p, r in _container_routes():
        if m != "GET":
            continue
        for role in ROLES:
            if matrix[key][role] == 403:
                continue
            got = client.request(m, _url(p, r, own), headers=tokens[role]).status_code
            if got in (401, 403, 404) and key not in EMPTY_IS_404:
                hidden.append(f"{key} [{role}] → {got}")
    assert not hidden, "Własny kontener niewidoczny:\n" + "\n".join(hidden)


# świadome 404 dla pustego zasobu (nie brak dostępu)
EMPTY_IS_404 = {"GET /api/containers/{container_id}/attachments/zip"}  # „Brak załączników.”
