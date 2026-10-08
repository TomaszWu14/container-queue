# Plaster 2: mutacje koszyka/konsolidacji (backend) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development / executing-plans.

**Goal:** Endpointy zmieniające przypisanie zamówień do kontenerów i cykl życia koszyka (przypisz/odepnij/zwolnij/zablokuj/zamknij konsolidację), z guardem „zamknięty→400", izolacją spółki i audytem.

**Architecture:** Dokłada mutacje do istniejącego routera `app/routers/consolidation.py` (plaster 1). Używa `record_changes` (ustawia pole + audyt), `can_add_order` (plaster 1), guardów ról z `deps`.

**Tech Stack:** FastAPI, SQLAlchemy, pytest.

## Global Constraints
- Guardy ról (ZAŁOŻENIE, do korekty): przypisanie/odpięcie/blokada/odblokowanie/zamknięcie konsolidacji = `admin + logistics` (Dział Transportu = na razie logistics). Zwolnienie zamówienia = `admin + logistics + purchasing` (Kupiec).
- Izolacja spółki na każdej mutacji: kontener/zamówienie spoza scope → 404 (nie zdradzamy istnienia).
- Kolejność stanów (gating: czy zwolnione przed przypisaniem) **poza zakresem** — ustawiamy pola wprost; egzekwowanie kolejności to plaster CRD.
- Każda mutacja → audyt przez `record_changes` + `db.commit()`.
- Reużyj `_po_dict` i wzorca scope z istniejącego `consolidation.py`.

---

### Task 1: Helpery scope + mutacje przypisania (assign/remove)

**Files:**
- Modify: `backend/app/routers/consolidation.py`
- Test: `backend/tests/test_koszyk_mutacje.py`

**Interfaces:**
- Consumes: `can_add_order` (`app.consolidation`), `record_changes` (`app.audit`), `company_filter_ids` (`app.deps`), `require_roles`/`Role` (`app.security`/`app.models`), `_po_dict` (istniejące w consolidation.py).
- Produces: `PUT /api/containers/{cid}/orders/{po_id}`, `DELETE /api/containers/{cid}/orders/{po_id}`; helpery `_scoped_container(db, cid, user)`, `_scoped_po(db, po_id, user)`.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_koszyk_mutacje.py
from app.database import SessionLocal
from app.models import Company, Container, PurchaseOrder, CartStatus, ConsolidationStatus
# admin_headers: fixtura jak w tests/test_customs.py; login helper stamtąd
from tests.test_customs import login  # jeśli nie eksportowane — skopiuj wzorzec logowania admina


def _seed(db):
    co = db.query(Company).first()
    cont = Container(container_no="KMCU0000001", company_id=co.id)
    db.add(cont); db.flush()
    po = PurchaseOrder(company_id=co.id, order_no="KM-A", cbm=5,
                       cart_status=CartStatus.zwolnione.value)
    db.add(po); db.commit()
    return cont.id, po.id


def test_assign_and_remove(client, admin_headers):
    with SessionLocal() as db:
        cid, pid = _seed(db)
    r = client.put(f"/api/containers/{cid}/orders/{pid}", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["cart_status"] == "przypisane"
    assert r.json()["container_id"] == cid
    d = client.delete(f"/api/containers/{cid}/orders/{pid}", headers=admin_headers)
    assert d.status_code == 200 and d.json()["container_id"] is None
    assert d.json()["cart_status"] == "w_koszyku"


def test_assign_to_closed_container_400(client, admin_headers):
    with SessionLocal() as db:
        cid, pid = _seed(db)
        cont = db.get(Container, cid)
        cont.consolidation_status = ConsolidationStatus.zamkniety.value
        db.commit()
    r = client.put(f"/api/containers/{cid}/orders/{pid}", headers=admin_headers)
    assert r.status_code == 400
    assert "zamkni" in r.json()["detail"].lower()
```

Uwaga: jeśli `from tests.test_customs import login` nie działa, użyj tego samego wzorca logowania co inne testy z `admin_headers` (podejrzyj `conftest.py`/`test_customs.py`); `admin_headers` wystarcza (admin widzi wszystko — scope przechodzi).

- [ ] **Step 2: Run — expect FAIL (404/route missing)**

Run: `cd backend && python -m pytest tests/test_koszyk_mutacje.py -v`
Expected: FAIL (endpoint nie istnieje → 405/404)

- [ ] **Step 3: Implement helpery + endpointy w consolidation.py**

Dodaj importy (na górze pliku, obok istniejących):
```python
from fastapi import HTTPException, status
from ..audit import record_changes
from ..consolidation import can_add_order, container_crd, container_fill_cbm
from ..deps import company_filter_ids
from ..models import CartStatus, ConsolidationStatus, Container, PurchaseOrder, Role, User
from ..security import require_roles
```
(usuń duplikaty importów, jeśli plaster 1 już je wniósł)

Dodaj deps ról i helpery:
```python
_editors = Depends(require_roles(Role.admin, Role.logistics))
_releasers = Depends(require_roles(Role.admin, Role.logistics, Role.purchasing))


def _scoped_container(db, cid: int, user: User) -> Container:
    cont = db.get(Container, cid)
    ids = company_filter_ids(user)
    if cont is None or (ids is not None and cont.company_id not in ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kontener nie istnieje.")
    return cont


def _scoped_po(db, po_id: int, user: User) -> PurchaseOrder:
    po = db.get(PurchaseOrder, po_id)
    ids = company_filter_ids(user)
    if po is None or (ids is not None and po.company_id not in ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zamówienie nie istnieje.")
    return po
```

Endpointy:
```python
@router.put("/containers/{cid}/orders/{po_id}")
def assign_order(cid: int, po_id: int, db: Session = Depends(get_db), user: User = _editors) -> dict:
    cont = _scoped_container(db, cid, user)
    po = _scoped_po(db, po_id, user)
    if not can_add_order(cont):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kontener zamknięty — nie można dodać zamówienia.")
    record_changes(db, po, {"container_id": cid, "cart_status": CartStatus.przypisane.value},
                   user, note="przypisano do kontenera")
    db.commit(); db.refresh(po)
    return _po_dict(po)


@router.delete("/containers/{cid}/orders/{po_id}")
def remove_order(cid: int, po_id: int, db: Session = Depends(get_db), user: User = _editors) -> dict:
    po = _scoped_po(db, po_id, user)
    if po.container_id != cid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zamówienia nie ma w tym kontenerze.")
    record_changes(db, po, {"container_id": None, "cart_status": CartStatus.w_koszyku.value},
                   user, note="odpięto z kontenera")
    db.commit(); db.refresh(po)
    return _po_dict(po)
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd backend && python -m pytest tests/test_koszyk_mutacje.py -v`
Expected: PASS (2 testy)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/consolidation.py backend/tests/test_koszyk_mutacje.py
git commit -m "feat(front): mutacje przypisania zamowienia do kontenera (assign/remove)"
```

---

### Task 2: Zwolnienie / blokada / zamknięcie konsolidacji

**Files:**
- Modify: `backend/app/routers/consolidation.py`
- Test: `backend/tests/test_koszyk_mutacje.py` (dopisać)

**Interfaces:**
- Produces: `POST /api/purchase-orders/{po_id}/release`, `POST /api/purchase-orders/{po_id}/block`, `POST /api/purchase-orders/{po_id}/unblock`, `POST /api/containers/{cid}/close-consolidation`.

- [ ] **Step 1: Write failing tests**

```python
# dopisz do backend/tests/test_koszyk_mutacje.py
from app.consolidation import container_fill_cbm


def test_release_sets_zwolnione(client, admin_headers):
    with SessionLocal() as db:
        co = db.query(Company).first()
        po = PurchaseOrder(company_id=co.id, order_no="KM-R", cart_status=CartStatus.w_koszyku.value)
        db.add(po); db.commit(); pid = po.id
    r = client.post(f"/api/purchase-orders/{pid}/release", headers=admin_headers)
    assert r.status_code == 200 and r.json()["cart_status"] == "zwolnione"


def test_block_excludes_from_fill(client, admin_headers):
    with SessionLocal() as db:
        co = db.query(Company).first()
        cont = Container(container_no="KMCU0000009", company_id=co.id); db.add(cont); db.flush()
        po = PurchaseOrder(company_id=co.id, order_no="KM-B", cbm=8, container_id=cont.id,
                           cart_status=CartStatus.przypisane.value)
        db.add(po); db.commit(); cid, pid = cont.id, po.id
        assert container_fill_cbm(db, cid) == 8.0
    r = client.post(f"/api/purchase-orders/{pid}/block", headers=admin_headers)
    assert r.status_code == 200 and r.json()["cart_status"] == "zablokowane"
    with SessionLocal() as db:
        assert container_fill_cbm(db, cid) == 0.0   # zablokowane wypada


def test_close_consolidation_blocks_assign(client, admin_headers):
    with SessionLocal() as db:
        co = db.query(Company).first()
        cont = Container(container_no="KMCU0000010", company_id=co.id); db.add(cont); db.flush()
        po = PurchaseOrder(company_id=co.id, order_no="KM-C", cart_status=CartStatus.zwolnione.value)
        db.add(po); db.commit(); cid, pid = cont.id, po.id
    c = client.post(f"/api/containers/{cid}/close-consolidation", headers=admin_headers)
    assert c.status_code == 200 and c.json()["consolidation_status"] == "zamkniety"
    r = client.put(f"/api/containers/{cid}/orders/{pid}", headers=admin_headers)
    assert r.status_code == 400
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd backend && python -m pytest tests/test_koszyk_mutacje.py -k "release or block or close" -v`
Expected: FAIL (endpointy nie istnieją)

- [ ] **Step 3: Implement endpointy**

```python
@router.post("/purchase-orders/{po_id}/release")
def release_order(po_id: int, db: Session = Depends(get_db), user: User = _releasers) -> dict:
    po = _scoped_po(db, po_id, user)
    record_changes(db, po, {"cart_status": CartStatus.zwolnione.value}, user, note="zwolnienie do odbioru")
    db.commit(); db.refresh(po)
    return _po_dict(po)


@router.post("/purchase-orders/{po_id}/block")
def block_order(po_id: int, db: Session = Depends(get_db), user: User = _editors) -> dict:
    po = _scoped_po(db, po_id, user)
    record_changes(db, po, {"cart_status": CartStatus.zablokowane.value}, user, note="blokada zamówienia")
    db.commit(); db.refresh(po)
    return _po_dict(po)


@router.post("/purchase-orders/{po_id}/unblock")
def unblock_order(po_id: int, db: Session = Depends(get_db), user: User = _editors) -> dict:
    po = _scoped_po(db, po_id, user)
    record_changes(db, po, {"cart_status": CartStatus.w_koszyku.value}, user, note="odblokowano zamówienie")
    db.commit(); db.refresh(po)
    return _po_dict(po)


@router.post("/containers/{cid}/close-consolidation")
def close_consolidation(cid: int, db: Session = Depends(get_db), user: User = _editors) -> dict:
    cont = _scoped_container(db, cid, user)
    record_changes(db, cont, {"consolidation_status": ConsolidationStatus.zamkniety.value},
                   user, note="zamknięto konsolidację")
    db.commit()
    return {"id": cont.id, "consolidation_status": cont.consolidation_status}
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd backend && python -m pytest tests/test_koszyk_mutacje.py -v`
Expected: PASS (wszystkie)

- [ ] **Step 5: Regresja izolacji + konsolidacji**

Run: `cd backend && python -m pytest tests/test_koszyk_mutacje.py tests/test_consolidation.py tests/test_deps.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/consolidation.py backend/tests/test_koszyk_mutacje.py
git commit -m "feat(front): zwolnienie/blokada/zamkniecie konsolidacji + testy"
```

---

## Poza zakresem (kolejne plastry)
UI koszyka (frontend); egzekwowanie kolejności stanów (zwolnione przed przypisaniem); auto-`wypelniony` gdy fill≥capacity; CRD odchylenie/eskalacja; SAP.
