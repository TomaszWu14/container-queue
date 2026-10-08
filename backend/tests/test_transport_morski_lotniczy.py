"""Główny transport kontenera: morski / lotniczy / kolej — z zamówienia i z importu kolejki."""
import pytest

from app.importers.queue import _classify_transport
from app.models import TransportType


@pytest.mark.parametrize("mode,expected", [("SEA", "morski"), ("AIR", "lotniczy"), ("RAIL", "kolej")])
def test_found_order_mode_sets_container_transport(client, admin_headers, mode, expected):
    companies = client.get("/api/companies", headers=admin_headers).json()
    cobalt = next(c["id"] for c in companies if c["code"] == "COBALT")
    resp = client.post("/api/zlecenia", headers=admin_headers, json={
        "number": f"ZL-{mode}", "company_id": cobalt, "container_count": 1, "main_mode": mode})
    assert resp.status_code == 201
    assert [c["transport_type"] for c in resp.json()["containers"]] == [expected]


@pytest.mark.parametrize("text,expected,detail", [
    ("morski", TransportType.morski, ""),
    ("SEA FCL", TransportType.morski, "SEA FCL"),
    ("statek + koła", TransportType.morski, "statek + koła"),
    ("lotniczy", TransportType.lotniczy, ""),
    ("Air cargo", TransportType.lotniczy, "Air cargo"),
    ("kolej", TransportType.kolej, ""),
    ("koła", TransportType.kola, ""),
    ("repair", None, "repair"),     # „air” tylko jako całe słowo
    ("", None, ""),
])
def test_classify_transport(text, expected, detail):
    assert _classify_transport(text) == (expected, detail)
