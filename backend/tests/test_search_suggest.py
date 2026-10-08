"""Podpowiedzi wyszukiwarki (2026-09-24): typ trafienia (kontener/PO/statek/dostawca),
limit 10, minimum 2 znaki, normalizacja i przycięcie do 50 znaków, separacja spółek."""
from app.routers.search import normalize_query
from .conftest import login
from .test_api import _company_id, _make_user


def _add(client, headers, company_id, no, **kw):
    r = client.post("/api/containers", headers=headers,
                    json={"container_no": no, "company_id": company_id, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_suggest_types_and_scope(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    other = _company_id(client, admin_headers, "ACME")
    cid = _add(client, admin_headers, borealis, "MSDU0806613", order_numbers="4500617421\n4500099999",
               vessel="MV DEMO ATLAS")
    _add(client, admin_headers, other, "TCLU1234568", vessel="MV DEMO MERIDIAN")

    def sug(q, headers=admin_headers):
        return client.get("/api/search/suggest", params={"q": q}, headers=headers).json()

    assert sug("M") == []                                   # < 2 znaki
    hit = sug("0806")[0]
    assert (hit["type"], hit["label"], hit["container_id"]) == ("container", "MSDU0806613", cid)
    assert sug("99999")[0] == {**sug("99999")[0], "type": "po", "label": "4500099999"}
    assert {s["type"] for s in sug("demo")} == {"vessel"}
    assert sug("  4500617421\n ")[0]["type"] == "po"         # białe znaki/nowe linie znormalizowane

    _make_user(client, admin_headers, "log.sug", "logistics", borealis)
    scoped = sug("demo", login(client, "log.sug", "haslo123"))
    assert [s["container_no"] for s in scoped] == ["MSDU0806613"]   # bez kontenera innej spółki


def test_suggest_limit_and_normalize(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    from app.iso6346 import check_digit
    bases = [b for b in (f"TSTU{100100 + i:06d}" for i in range(30)) if check_digit(b) < 10][:12]
    for base in bases:   # cyfra kontrolna 10 = numer odrzucany przez walidację
        _add(client, admin_headers, borealis, f"{base}{check_digit(base)}", vessel="MV DEMO TEST")
    assert len(client.get("/api/search/suggest", params={"q": "tstu"}, headers=admin_headers).json()) == 10
    # statek 12 kontenerów = JEDNA podpowiedź (wybór filtruje kolejkę po statku)
    assert len(client.get("/api/search/suggest", params={"q": "demo test"}, headers=admin_headers).json()) == 1
    assert normalize_query("  a \n\t b  ") == "a b"
    assert len(normalize_query("x" * 80)) == 50


def _sug(client, headers, q, **params):
    r = client.get("/api/search/suggest", params={"q": q, **params}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_suggest_balanced_types_dedup_and_long_q(client, admin_headers):
    """Podział między typy: 12 trafień po numerze kontenera nie wypycha PO/statku/dostawcy,
    a statek/PO/dostawca pojawiają się raz (nie 12×). q > 50 znaków → przycięte, nie 422."""
    from app.iso6346 import check_digit
    borealis = _company_id(client, admin_headers, "BOREALIS")
    sup = client.post("/api/suppliers", headers=admin_headers,
                      json={"name": "EVRU Supplies", "company_id": borealis}).json()
    bases = [b for b in (f"EVRU{200100 + i:06d}" for i in range(30)) if check_digit(b) < 10][:12]
    for base in bases:
        _add(client, admin_headers, borealis, f"{base}{check_digit(base)}", vessel="EVRU ONE",
             order_numbers="EVRU-PO1", supplier_id=sup["id"])
    out = _sug(client, admin_headers, "evru")
    assert len(out) == 10
    kinds = [s["type"] for s in out]
    assert kinds.count("vessel") == kinds.count("supplier") == kinds.count("po") == 1
    assert kinds[:4] == ["container", "po", "vessel", "supplier"]   # na zmianę, od kontenera
    assert next(s for s in out if s["type"] == "supplier")["supplier_id"] == sup["id"]
    # 4 + 3 spacje + 60 → po normalizacji i przycięciu do 50: „evru x…x” — brak trafień, bez 422
    assert _sug(client, admin_headers, "evru" + " " * 3 + "x" * 60) == []
    # białe znaki (także 60 nowych linii) → jedna spacja, zanim zadziała przycięcie
    assert _sug(client, admin_headers, "evru" + "\n" * 60 + "one")[0]["type"] == "vessel"


def test_suggest_roles_see_only_their_queue(client, admin_headers):
    """Spedytor / agencja / magazyn widzą w podpowiedziach tylko swoje kontenery; magazyn
    i agencja nie dostają trafień po PO ani dostawcy (te dane są maskowane w kolejce)."""
    from .test_api import forwarder
    from .test_customs import _agency
    borealis = _company_id(client, admin_headers, "BOREALIS")
    wh = client.post("/api/warehouses", headers=admin_headers, json={
        "name": "DLT", "company_id": borealis, "country": "PL"}).json()
    ag = _agency(client, admin_headers, "SUG-CELNA")
    fwd = forwarder(client, admin_headers, "SPEDALFA")
    sup = client.post("/api/suppliers", headers=admin_headers,
                      json={"name": "Tajny Dostawca", "company_id": borealis}).json()
    mine = _add(client, admin_headers, borealis, "MSDU0806613", vessel="ROLE SHIP",
                order_numbers="4500055555", supplier_id=sup["id"], warehouse_id=wh["id"],
                forwarder_id=fwd["id"])
    assert client.post(f"/api/customs/containers/{mine}/assign", headers=admin_headers,
                       json={"customs_agency_id": ag["id"]}).status_code == 200
    _add(client, admin_headers, borealis, "TCLU1234568", vessel="ROLE SHIP")   # poza zakresem ról
    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.sug", "password": "haslo123", "role": "forwarder",
        "forwarder_id": fwd["id"]})
    client.post("/api/users", headers=admin_headers, json={
        "login": "celna.sug", "password": "haslo123", "role": "customs",
        "customs_agency_id": ag["id"]})
    _make_user(client, admin_headers, "mag.sug", "warehouse", borealis, warehouse_id=wh["id"])

    assert len(_sug(client, admin_headers, "tclu")) == 1
    for who in ("sped.sug", "celna.sug", "mag.sug"):
        h = login(client, who, "haslo123")
        assert _sug(client, h, "tclu") == [], who                       # cudzy kontener
        assert [s["container_id"] for s in _sug(client, h, "msdu")] == [mine], who
        assert [s["container_id"] for s in _sug(client, h, "role ship")] == [mine], who
    for who in ("celna.sug", "mag.sug"):
        h = login(client, who, "haslo123")
        assert _sug(client, h, "4500055") == [] and _sug(client, h, "tajny") == [], who
    assert _sug(client, login(client, "sped.sug", "haslo123"), "4500055")[0]["type"] == "po"


def test_suggest_completed_filter(client, admin_headers):
    """Kolejka pyta completed=false (bez zrealizowanych), archiwum completed=true."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    cid = _add(client, admin_headers, borealis, "MSDU0806613")
    assert client.post(f"/api/containers/{cid}/status", headers=admin_headers,
                       json={"status": "ZREALIZOWANY"}).status_code == 200
    assert _sug(client, admin_headers, "0806", completed="false") == []
    assert _sug(client, admin_headers, "0806", completed="true")[0]["container_id"] == cid
