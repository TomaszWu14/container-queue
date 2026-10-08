"""Audyt DATA-004, decyzja właściciela 2026-09-28 (wariant a): numer z resztą 10 i cyfrą
kontrolną 0 jest poprawny wg ISO 6346 — przyjmujemy go z ostrzeżeniem zamiast odrzucać
(sync pomijał taki kontener po cichu)."""
from app import iso6346


def test_remainder_ten_with_zero_accepted_with_warning():
    ok, msg = iso6346.validate("TCNU0000080")
    assert ok and msg.startswith("Uwaga")


def test_remainder_ten_with_other_digit_rejected():
    ok, msg = iso6346.validate("TCNU0000081")
    assert not ok and "powinna być 0" in msg


def test_regular_number_unchanged():
    assert iso6346.validate("MSDU0806613") == (True, "")


def test_container_with_remainder_ten_can_be_created(client, admin_headers):
    company_id = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    r = client.post("/api/containers", headers=admin_headers,
                    json={"container_no": "TCNU0000080", "company_id": company_id})
    assert r.status_code in (200, 201), r.text
