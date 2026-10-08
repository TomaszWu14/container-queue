"""#5 — filtry per kolumna na /api/containers (tekst ILIKE, enum, zakres ETA)."""


def _company(client, headers, code="BOREALIS"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _mk(client, headers, cid, no, **extra):
    r = client.post("/api/containers", headers=headers,
                    json={"container_no": no, "company_id": cid, **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_text_and_range_filters(client, admin_headers):
    cid = _company(client, admin_headers)
    a = _mk(client, admin_headers, cid, "MSDU0806613",
            vessel="MV DEMO LYRA", order_numbers="4500619730", eta="2026-07-10")
    b = _mk(client, admin_headers, cid, "MSKU0000006",
            vessel="MV DEMO PALLAS", order_numbers="4500623968", eta="2026-08-20")

    def ids(qs):
        return {c["id"] for c in client.get(f"/api/containers?{qs}", headers=admin_headers).json()}

    # tekst (ILIKE, częściowy, case-insensitive)
    assert ids("vessel=lyra") == {a}
    assert ids("order_numbers=623968") == {b}
    # enum transport
    # zakres ETA
    assert ids("eta_from=2026-08-01") == {b}
    assert ids("eta_to=2026-07-31") == {a}
    assert ids("eta_from=2026-07-01&eta_to=2026-12-31") == {a, b}
    # brak filtra → oba
    assert {a, b} <= ids("company_code=BOREALIS")


def test_enum_filter_empty_sentinel_no_422(client, admin_headers):
    """C3: sentinel 'empty' na filtrze enuma NIE może dawać 422 (IS NULL → pusty wynik)."""
    for qs in ("status=empty", "customs_status=empty", "transport=empty"):
        r = client.get(f"/api/containers?{qs}", headers=admin_headers)
        assert r.status_code == 200, f"{qs} → {r.status_code} {r.text}"


def test_enum_filter_invalid_value_422(client, admin_headers):
    """C3: nieprawidłowa wartość enuma → jawny 422, nie cichy pusty wynik."""
    for qs in ("status=NONSENSE", "customs_status=XXX", "transport=samolot"):
        r = client.get(f"/api/containers?{qs}", headers=admin_headers)
        assert r.status_code == 422, f"{qs} → {r.status_code} {r.text}"


def test_enum_filter_valid_value_filters(client, admin_headers):
    """C3: prawidłowa wartość enuma dalej filtruje."""
    cid = _company(client, admin_headers)
    a = _mk(client, admin_headers, cid, "MSDU0806613", status="W_TRANSPORCIE")
    ids = {c["id"] for c in client.get(
        "/api/containers?status=W_TRANSPORCIE", headers=admin_headers).json()}
    assert a in ids
    ids2 = {c["id"] for c in client.get(
        "/api/containers?status=ZREALIZOWANY", headers=admin_headers).json()}
    assert a not in ids2
