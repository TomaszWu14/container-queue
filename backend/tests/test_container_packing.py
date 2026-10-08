"""Packer 3D kontenera (app/packing) + endpoint /api/containers/{id}/packing."""
from types import SimpleNamespace

from sqlalchemy import select

from app.models import Container, ContainerType, MaterialUnit, Order, OrderItem
from app.packing import container_inner_dims_cm, pack_container

DIMS_20FT = (589.0, 235.0, 239.0)


def _item(material, qty, unit="KAR", order_no="4500000001"):
    return SimpleNamespace(order_number=order_no, material=material,
                           quantity=str(qty), unit=unit)


def _marm(material, unit="KAR", length=None, width=None, height=None,
          dimension_unit="", volume=None, volume_unit="", numerator=1, denominator=1):
    return MaterialUnit(material_no=material, unit=unit, numerator=numerator,
                        denominator=denominator, volume=volume, volume_unit=volume_unit,
                        length=length, width=width, height=height,
                        dimension_unit=dimension_unit)


def _rows(*units):
    out: dict[str, list] = {}
    for u in units:
        out.setdefault(u.material_no, []).append(u)
    return out


def test_mono_sku_blocks_before_mixed_leftovers():
    # SKU A dominuje objętością -> jego blok mono zaczyna się w x=0; resztki obu SKU
    # (niepełne plastry) lądują w puli mieszanej ZA blokami mono.
    rows = _rows(_marm("A", length=100, width=100, height=100, dimension_unit="CM"),
                 _marm("B", length=50, width=50, height=50, dimension_unit="CM"))
    result = pack_container([_item("A", 8), _item("B", 3)], DIMS_20FT, rows)
    assert result["status"] == "ok"
    a_boxes = [b for b in result["boxes"] if b["sku"] == "A"]
    b_boxes = [b for b in result["boxes"] if b["sku"] == "B"]
    assert len(a_boxes) == 8 and len(b_boxes) == 3
    # blok mono A: pełne plastry 2×2 (W//100=2, H//100=2) od x=0
    mono_a_max_x = max(b["x"] for b in a_boxes[:8])
    assert min(b["x"] for b in a_boxes) == 0.0
    # pula mieszana zaczyna się za blokami mono
    assert all(b["x"] >= mono_a_max_x for b in b_boxes)
    assert result["excluded"] == []


def test_packing_is_deterministic():
    rows = _rows(_marm("A", length=60, width=40, height=40, dimension_unit="CM"),
                 _marm("B", length=55, width=35, height=30, dimension_unit="CM"))
    items = [_item("A", 37), _item("B", 23)]
    assert pack_container(items, DIMS_20FT, rows) == pack_container(items, DIMS_20FT, rows)


def test_overflow_goes_to_excluded_and_fill_over_100():
    # 1 m³ kartony × 40 szt = 40 m³ > ~33 m³ (20') -> część nie wchodzi
    rows = _rows(_marm("A", length=100, width=100, height=100, dimension_unit="CM"))
    result = pack_container([_item("A", 40)], DIMS_20FT, rows)
    assert result["fill_pct"] > 100
    overflow = [e for e in result["excluded"] if e["reason"] == "nie zmieściło się"]
    assert overflow and overflow[0]["material"] == "A"
    assert len(result["boxes"]) < 40


def test_large_mixed_pool_uses_fast_fallback():
    # duża pula mieszana (> PY3DBP_POOL_CAP) musi się policzyć szybko (bez py3dbp)
    # i deterministycznie; resztki, które nie wchodzą, lądują w excluded
    import time
    rows = {}
    items = []
    for i in range(30):
        m = f"M{i:03d}"
        rows[m] = [_marm(m, length=40 + (i % 3) * 10, width=30 + (i % 2) * 10,
                         height=20 + (i % 3) * 10, dimension_unit="CM")]
        items.append(_item(m, 5 + i))
    start = time.monotonic()
    result = pack_container(items, DIMS_20FT, {k: v for k, v in rows.items()})
    elapsed = time.monotonic() - start
    assert elapsed < 10, f"packer za wolny: {elapsed:.1f}s"
    assert result == pack_container(items, DIMS_20FT, rows)   # determinizm
    assert len(result["boxes"]) + sum(
        1 for e in result["excluded"] if e["reason"] == "nie zmieściło się") > 0


def test_cube_fallback_from_volume():
    # brak wymiarów, jest objętość 0.125 m³ -> sześcian 50 cm, approximated
    rows = _rows(_marm("A", volume=0.125, volume_unit="M3"))
    result = pack_container([_item("A", 2)], DIMS_20FT, rows)
    assert [b["approximated"] for b in result["boxes"]] == [True, True]
    assert result["boxes"][0]["w"] == result["boxes"][0]["h"] == result["boxes"][0]["d"] == 50.0


def test_no_marm_data_excluded_with_reason():
    result = pack_container([_item("A", 5), _item("", 1)], DIMS_20FT, {})
    assert result["status"] == "no_data" and result["boxes"] == []
    assert all("brak danych MARM" in e["reason"] for e in result["excluded"])


def test_bad_quantity_excluded():
    rows = _rows(_marm("A", length=50, width=50, height=50, dimension_unit="CM"))
    result = pack_container([_item("A", "dużo")], DIMS_20FT, rows)
    assert result["excluded"][0]["reason"] == "nieprawidłowa ilość"


def test_container_inner_dims_from_dict_and_fallback():
    assert container_inner_dims_cm(SimpleNamespace(
        name="20'DV", inner_length_m=5.90, inner_width_m=2.35,
        inner_height_m=2.39)) == (590.0, 235.0, 239.0)
    assert container_inner_dims_cm(SimpleNamespace(
        name="40'HC", inner_length_m=None, inner_width_m=None,
        inner_height_m=None)) == (1203.0, 235.0, 269.0)
    assert container_inner_dims_cm(SimpleNamespace(
        name="TANK", inner_length_m=None, inner_width_m=None,
        inner_height_m=None)) is None
    assert container_inner_dims_cm(None) is None


# --- endpoint ---

def _seed_container(client, admin_headers, db_session, company_code="ACME",
                    with_type=True, with_items=True, no="MSKU5696108"):
    companies = client.get("/api/companies", headers=admin_headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == company_code)
    created = client.post("/api/containers", headers=admin_headers,
                          json={"container_no": no, "company_id": company_id})
    assert created.status_code in (200, 201), created.text
    container_id = created.json()["id"]
    order = Order(number=f"Z-{no}", company_id=company_id)
    if with_type:
        order.container_type_id = db_session.scalars(
            select(ContainerType).where(ContainerType.name == "20'DV")).one().id
    db_session.add(order)
    db_session.flush()
    values = {"order_id": order.id}
    if with_items:
        values["order_numbers"] = "4500011111"
        db_session.add(OrderItem(company_id=company_id, order_number="4500011111",
                                 material="100200", quantity="3", unit="KAR"))
        db_session.add(MaterialUnit(material_no="100200", unit="KAR", length=600,
                                    width=400, height=300, dimension_unit="MM"))
    db_session.query(Container).filter(Container.id == container_id).update(values)
    db_session.commit()
    return container_id


def test_packing_endpoint_ok_shape(client, admin_headers, db_session):
    cid = _seed_container(client, admin_headers, db_session)
    r = client.get(f"/api/containers/{cid}/packing", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert len(body["boxes"]) == 3
    box = body["boxes"][0]
    assert set(box) == {"x", "y", "z", "w", "h", "d", "sku", "color", "approximated"}
    assert body["container_dims"] == {"l": 590.0, "w": 235.0, "h": 239.0}
    assert body["volume_total_m3"] > 0 and body["fill_pct"] > 0


def test_packing_endpoint_no_type_and_no_items(client, admin_headers, db_session):
    cid = _seed_container(client, admin_headers, db_session, with_type=False,
                          no="MSDU0806613")
    assert client.get(f"/api/containers/{cid}/packing",
                      headers=admin_headers).json()["status"] == "no_type"
    cid2 = _seed_container(client, admin_headers, db_session, with_items=False,
                           no="TRHU1306972")
    assert client.get(f"/api/containers/{cid2}/packing",
                      headers=admin_headers).json()["status"] == "no_items"


def test_packing_endpoint_company_isolation(client, admin_headers, db_session):
    from tests.test_isolation import _company_id, _make_scoped_user
    cid = _seed_container(client, admin_headers, db_session, company_code="BOREALIS",
                          no="MSNU2506240")
    b_id = _company_id(client, admin_headers, "COBALT")
    headers_b = _make_scoped_user(client, admin_headers, "intruz.pack", b_id)
    r = client.get(f"/api/containers/{cid}/packing", headers=headers_b)
    assert r.status_code in (403, 404), f"IDOR: B odczytał packing kontenera A ({r.status_code})"
