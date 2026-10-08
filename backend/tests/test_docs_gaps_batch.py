"""PERF-004: /customs/docs-gaps i check_docs_alerts liczą braki dokumentów wsadowo
(stała liczba zapytań niezależnie od liczby kontenerów), z wynikiem identycznym
jak reguła per kontener."""
import datetime

from sqlalchemy import select

from app.models import (Attachment, Company, Container, CustomsStatus, DocumentType,
                        today_pl)
from app.routers.customs import in_customs_flow, missing_document_types
from tests.test_query_bounds import _count_statements, _numbers


def _seed(db, count, tag="A"):
    company = db.scalar(select(Company).where(Company.code == "ACME"))
    types = [DocumentType(name=f"PERF {tag}{i}", is_required=True, sort_order=i)
             for i in range(3)]
    db.add_all(types)
    eta = today_pl() + datetime.timedelta(days=1)
    containers = []
    for i, no in enumerate(_numbers(count, prefix=f"PRF{tag}")):
        c = Container(container_no=no, company_id=company.id, eta=eta,
                      customs_status=CustomsStatus.ZLECONA if i % 5 else CustomsStatus.BRAK)
        db.add(c)
        containers.append(c)
    db.flush()
    for i, c in enumerate(containers):   # różne kombinacje kompletności
        for j, dt in enumerate(types):
            if (i >> j) & 1:
                db.add(Attachment(container_id=c.id, filename="x.pdf",
                                  stored_name=f"perf-{c.id}-{dt.id}", document_type_id=dt.id))
    db.commit()
    return containers


def _gaps_statements(client, headers):
    with _count_statements() as counter:
        resp = client.get("/api/customs/docs-gaps", headers=headers)
    assert resp.status_code == 200, resp.text
    return counter["n"], resp.json()


def test_docs_gaps_query_count_does_not_grow(client, admin_headers, db_session):
    _seed(db_session, 5, "A")
    few, _ = _gaps_statements(client, admin_headers)
    _seed(db_session, 20, "B")
    many, gaps = _gaps_statements(client, admin_headers)
    assert len(gaps) >= 10
    assert many <= few + 2, (few, many)   # przed poprawką: 11 → 42


def test_docs_gaps_matches_per_container_rule(client, admin_headers, db_session):
    containers = _seed(db_session, 20)
    _, gaps = _gaps_statements(client, admin_headers)
    expected = [{"id": c.id, "missing": missing_document_types(db_session, c)}
                for c in containers if in_customs_flow(c)]
    expected = [e for e in expected if e["missing"]]
    assert expected and all(e["missing"] for e in expected)
    assert sorted(({"id": g["id"], "missing": g["missing"]} for g in gaps),
                  key=lambda g: g["id"]) == sorted(expected, key=lambda g: g["id"])
