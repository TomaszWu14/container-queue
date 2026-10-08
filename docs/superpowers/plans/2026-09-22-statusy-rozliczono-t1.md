# Plaster: statusy Rozliczono + T1 (RFP §5.5) — Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Domknąć model statusów §5.5: dodać brakujący status celny `ROZLICZONY` (po ODPRAWIONY) i równoległy znacznik tranzytu celnego `T1` (odprawa poza portem). Wyłącznie ADDYTYWNIE — nie ruszamy istniejących statusów (zamrożony kontrakt).

**Architecture:** Nowy member `CustomsStatus.ROZLICZONY` (ustawialny przez istniejący `POST /containers/{id}/status`) + nowa kolumna bool `Container.customs_t1` (ustawiana opcjonalnie przez ten sam endpoint). Migracja addytywna + dev-shim + serializacja + i18n.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, React (i18n), pytest.

## Global Constraints
- ADDYTYWNIE: nie zmieniaj/nie usuwaj istniejących członów `CustomsStatus` ani `ContainerStatus` (zamrożony kontrakt; enum był już rozszerzany o DRAFT_* — ten sam wzorzec).
- Migracja addytywna, `down_revision` = obecna głowa alembica, JEDNA głowa. Kolumny nowe do dev-shim `ensure_new_columns` (main.py).
- T1 jest RÓWNOLEGŁY do obiegu (nie sekwencyjny status) → bool `customs_t1`, nie member enuma.
- Reużyj istniejącego `POST /api/customs/containers/{id}/status` (endpoint już przyjmuje `CustomsStatus`).

---

### Task 1: Status celny `ROZLICZONY`

**Files:** Modify `backend/app/models.py` (enum), `backend/app/routers/customs.py` (`_status_label`), `frontend/src/i18n.ts`; Test `backend/tests/test_customs.py`.

- [ ] **Step 1: Failing test**

```python
# dopisz do backend/tests/test_customs.py — wzoruj na istniejacych testach statusu odprawy
def test_customs_status_rozliczony(client, admin_headers):
    from app.models import Container, Company, CustomsStatus
    from app.database import SessionLocal
    with SessionLocal() as db:
        co = db.query(Company).first()
        c = Container(container_no="RLZU0000001", company_id=co.id,
                      customs_status=CustomsStatus.ODPRAWIONY.value)
        db.add(c); db.commit(); cid = c.id
    r = client.post(f"/api/customs/containers/{cid}/status", headers=admin_headers,
                    json={"customs_status": "ROZLICZONY"})
    assert r.status_code == 200, r.text
    assert r.json()["customs_status"] == "ROZLICZONY"
```

- [ ] **Step 2: Run — FAIL** (walidacja enuma odrzuci "ROZLICZONY")

- [ ] **Step 3: Implement**

W `models.py`, `class CustomsStatus`, PO `ODPRAWIONY` a przed `REWIZJA`:
```python
    ROZLICZONY = "ROZLICZONY"
```
W `customs.py` `_status_label` dict dodaj:
```python
        CustomsStatus.ROZLICZONY: "rozliczony",
```
W `frontend/src/i18n.ts` — dodaj etykietę statusu odprawy dla `ROZLICZONY` do WSZYSTKICH 3 słowników, spójnie z istniejącym wzorcem kluczy statusów celnych (np. jeśli jest `cs_ODPRAWIONY`, dodaj `cs_ROZLICZONY`: PL „Rozliczony" / EN „Settled" / PT „Liquidado"). Znajdź faktyczny prefiks kluczy statusów odprawy w i18n i użyj go.

- [ ] **Step 4: Run — PASS**; **Step 5: Commit** `feat(customs): status ROZLICZONY (RFP 5.5)`

---

### Task 2: Znacznik `T1` (tranzyt celny poza portem)

**Files:** Modify `backend/app/models.py` (Container), `backend/app/main.py` (dev-shim), `backend/app/schemas.py` (CustomsStatusIn + ContainerOut), `backend/app/routers/customs.py` (`update_status`), `frontend/src/i18n.ts`; Create migracja; Test `backend/tests/test_customs.py`.

- [ ] **Step 1: Failing test**

```python
def test_container_t1_flag(client, admin_headers):
    from app.models import Container, Company
    from app.database import SessionLocal
    with SessionLocal() as db:
        co = db.query(Company).first()
        c = Container(container_no="T1CU0000001", company_id=co.id)
        db.add(c); db.commit(); cid = c.id
    r = client.post(f"/api/customs/containers/{cid}/status", headers=admin_headers,
                    json={"customs_status": "ZLECONA", "customs_t1": True})
    assert r.status_code == 200, r.text
    assert r.json()["customs_t1"] is True
```

- [ ] **Step 2: Run — FAIL** (brak pola/kolumny)

- [ ] **Step 3: Implement**

`models.py`, `class Container` (obok innych bool jak `is_special`):
```python
    customs_t1: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
```
(wzorzec jak sąsiednie kolumny bool; `server_default="0"` dla istniejących wierszy)

`schemas.py`:
- `CustomsStatusIn`: dodaj `customs_t1: bool | None = None`.
- `ContainerOut`: dodaj `customs_t1: bool` (żeby front i test go widziały).

`customs.py` `update_status`: po zbudowaniu `changes`, jeśli `body.customs_t1 is not None`: `changes["customs_t1"] = body.customs_t1`.

Migracja `backend/migrations/versions/<rev>_container_customs_t1.py` (rev np. `t1flag001`, down_revision = obecna głowa — SPRAWDŹ `ScriptDirectory.get_heads()`):
```python
def upgrade():
    op.add_column('containers', sa.Column('customs_t1', sa.Boolean(), nullable=False, server_default='0'))
def downgrade():
    op.drop_column('containers', 'customs_t1')
```
Dev-shim `main.py` `ensure_new_columns`: dodaj `customs_t1` do listy kolumn `containers` (wzorzec jak inne bool).

i18n: klucz badge `t1Badge` (PL „T1 (tranzyt celny)" / EN „T1 (customs transit)" / PT „T1 (trânsito aduaneiro)") w 3 słownikach.

- [ ] **Step 4: Run — PASS**; **Step 5: single alembic head** (`ScriptDirectory.get_heads()` → dokładnie 1); **Step 6: Commit** `feat(customs): znacznik T1 tranzytu celnego (RFP 5.5)`

---

## Poza zakresem
Badge T1 + wybór ROZLICZONY w UI (tablica celna/karta) — drobny follow-up frontowy; tu backend + i18n keys. Faktura za odprawę/należności (osobny plaster). Rename statusów do 1:1 §5.5 — świadomie NIE (zamrożony kontrakt).
