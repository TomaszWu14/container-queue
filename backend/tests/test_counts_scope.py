"""Audyt UI C14/A17: licznik „Kolejka” w nawigacji sumuje /api/containers/counts — endpoint musi
liczyć wyłącznie kontenery w zakresie roli (spedytor: tylko swoje), nie globalnie."""
from tests.conftest import forwarder, login
from tests.test_api import VALID_NO, _company_id

OTHER_NO = "HLXU2733056"


def test_counts_scoped_to_forwarder(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    toll = forwarder(client, admin_headers, "Speddelta")["id"]
    client.post("/api/users", headers=admin_headers, json={
        "login": "sped.spedalfa", "password": "haslo123", "role": "forwarder",
        "forwarder_id": spedalfa, "email": "spedalfa@example.com"})
    for no, fwd in ((VALID_NO, spedalfa), (OTHER_NO, toll)):
        r = client.post("/api/containers", headers=admin_headers, json={
            "container_no": no, "company_id": borealis, "forwarder_id": fwd})
        assert r.status_code == 201, r.text

    admin_counts = client.get("/api/containers/counts", headers=admin_headers).json()
    dsv_counts = client.get("/api/containers/counts",
                            headers=login(client, "sped.spedalfa", "haslo123")).json()

    assert admin_counts["BOREALIS"] == 2
    assert dsv_counts["BOREALIS"] == 1            # tylko własny kontener spedytora
    assert sum(v for k, v in dsv_counts.items() if k != "DLT") == 1
