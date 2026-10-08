"""Strażnik (audyt 2026-09-23, P15): endpointy bez żadnego konsumenta usunięte —
nie wracają po cichu (np. przy rozwiązywaniu konfliktu merge)."""
import pytest

from app.main import app

REMOVED = [
    ("patch", "/api/container-types/{type_id}"),
    ("get", "/api/analysis/unload-times"),
    ("get", "/api/tracking/vessels/{vessel_id}/ports"),
    ("post", "/api/containers/{container_id}/documents/ocr"),
    ("get", "/api/stats/rfq"),
]


@pytest.mark.parametrize("method,path", REMOVED)
def test_removed_endpoint_not_routed(method, path):
    assert method not in app.openapi()["paths"].get(path, {})
