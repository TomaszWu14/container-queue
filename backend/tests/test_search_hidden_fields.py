"""Wyszukiwanie nie jest wyrocznią pól ukrytych (2026-09-25): magazyn i agencja celna nie
widzą PO ani dostawcy (to_out), więc szukanie po nich — kolejka ?q=, filtry kolumn, eksport
xlsx, podpowiedzi — daje 0 wyników. Reguła: containers_common.hidden_fields/searchable."""
from io import BytesIO

from openpyxl import load_workbook

from .conftest import login
from .test_api import VALID_NO, _company_id, _make_user

PO = "4500617421"
SUPPLIER = "Tajny Dostawca SA"
VESSEL = "MV DEMO ATLAS"


def _setup(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    cobalt = _company_id(client, admin_headers, "COBALT")
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "DLT", "company_id": borealis, "country": "PL"}).json()
    agency = client.post("/api/customs-agencies", headers=admin_headers,
                         json={"name": "CELNA-Q"}).json()
    supplier = client.post("/api/suppliers", headers=admin_headers, json={
        "name": SUPPLIER, "company_id": borealis}).json()
    cont = client.post("/api/containers", headers=admin_headers, json={
        "container_no": VALID_NO, "company_id": borealis, "warehouse_id": wh["id"],
        "supplier_id": supplier["id"],
        "order_numbers": PO, "vessel": VESSEL, "notes": "uwaga wewnętrzna"})
    assert cont.status_code == 201, cont.text
    cid = cont.json()["id"]
    r = client.post(f"/api/customs/containers/{cid}/assign", headers=admin_headers,
                    json={"customs_agency_id": agency["id"]})
    assert r.status_code == 200, r.text
    _make_user(client, admin_headers, "mag.q", "warehouse", borealis, warehouse_id=wh["id"])
    _make_user(client, admin_headers, "log.q", "logistics", borealis)
    _make_user(client, admin_headers, "log.y", "logistics", cobalt)
    r = client.post("/api/users", headers=admin_headers, json={
        "login": "celna.q", "password": "haslo123", "role": "customs",
        "customs_agency_id": agency["id"]})
    assert r.status_code == 201, r.text
    return cid, supplier["id"]


def _q(client, headers, **params):
    r = client.get("/api/containers", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return [c["id"] for c in r.json()]


def _sug(client, headers, q):
    return [s["container_id"] for s in
            client.get("/api/search/suggest", params={"q": q}, headers=headers).json()]


def test_restricted_roles_cannot_search_hidden_fields(client, admin_headers):
    cid, supplier_id = _setup(client, admin_headers)
    for who in ("mag.q", "celna.q"):
        h = login(client, who, "haslo123")
        # pola ukryte → 0 wyników (kolejka, archiwum, filtry kolumn, podpowiedzi)
        assert _q(client, h, q=PO) == []
        assert _q(client, h, q=PO, completed="false") == []
        assert _q(client, h, q="wewnętrzna") == []
        assert _sug(client, h, PO) == []
        assert _sug(client, h, "Tajny") == []
        # filtr kolumny po ukrytym polu jest ignorowany — wynik nie zależy od wartości
        assert _q(client, h, order_numbers=PO) == _q(client, h, order_numbers="0000") == [cid]
        assert _q(client, h, supplier_id=str(supplier_id)) == \
            _q(client, h, supplier_id=str(supplier_id + 999)) == [cid]
        # pola widoczne → wyniki
        assert _q(client, h, q=VALID_NO[:8]) == [cid]
        assert _q(client, h, q="demo") == [cid]
        assert _sug(client, h, VALID_NO[:8]) == [cid]
        sug = client.get("/api/search/suggest", params={"q": "demo"}, headers=h).json()
        assert [(s["type"], s["label"]) for s in sug] == [("vessel", VESSEL)]
        # eksport xlsx z ?q= po PO — tylko nagłówek
        x = client.get("/api/containers/export/xlsx", params={"q": PO}, headers=h)
        assert x.status_code == 200
        assert load_workbook(BytesIO(x.content)).active.max_row == 1


def test_full_roles_unchanged_and_isolation(client, admin_headers):
    cid, supplier_id = _setup(client, admin_headers)
    for h in (admin_headers, login(client, "log.q", "haslo123")):
        assert _q(client, h, q=PO) == [cid]
        assert _q(client, h, q="wewnętrzna") == [cid]
        assert _q(client, h, order_numbers=PO) == [cid]
        assert _q(client, h, supplier_id=str(supplier_id + 999)) == []
        assert _sug(client, h, PO) == [cid]
        assert _sug(client, h, "Tajny") == [cid]
    other = login(client, "log.y", "haslo123")   # inna spółka — nic nie widzi
    assert _q(client, other, q=PO) == []
    assert _sug(client, other, PO) == []
    assert _sug(client, other, "demo") == []
