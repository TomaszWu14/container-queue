# Tranzyty — dane klienta docelowego: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kontener tranzytowy (`is_transit=True`) przechowuje ręcznie wpisane dane klienta docelowego (nazwa, adres, kontakt), edytowalne przez logistykę, maskowane przed `warehouse` i `customs`.

**Architecture:** Rozszerzenie istniejącej flagi `is_transit` (zgodnie ze spec `2026-09-02-tranzyty-modul.md` — NIE osobny moduł). Trzy nowe kolumny tekstowe na `Container`, przepływ przez istniejące `ContainerCreate/Update/Out`, maskowanie wzorcem `_CUSTOMS_HIDDEN`/`_WAREHOUSE_HIDDEN` w `to_out()`. Front: sekcja „Klient docelowy" w `ContainerPage` z edycją inline dla ról edytujących. Ręczne DOSTARCZONY przez logistykę **już działa** (`change_status`, containers.py:676-682 ogranicza tylko magazyn) — zero zmian.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + pytest (backend/), React 19 + vitest (frontend/).

## Global Constraints

- Statusy/enums w `backend/app/models.py`; role przez `deps.py` — nie powielać reguł w routerach (CLAUDE.md).
- Każda zmiana pola kontenera → audyt `record(...)` / `record_changes(...)`.
- i18n: każdy nowy klucz w **trzech** słownikach `pl/en/pt` w `frontend/src/i18n.ts`.
- Testy backendu: z katalogu `backend/` → `pytest` (venv `backend/.venv`). Frontend: z `frontend/` → `npx vitest run`.
- Komunikaty UI Polish-first.

---

### Task 1: Backend — kolumny klienta + maskowanie

**Files:**
- Modify: `backend/app/models.py` (klasa `Container`, przy `is_transit` ~linia 356)
- Modify: `backend/app/schemas.py` (`ContainerBase` ~402, `ContainerUpdate` ~456, `ContainerOut` ~514)
- Modify: `backend/app/routers/containers.py` (`_WAREHOUSE_HIDDEN` ~105, `_CUSTOMS_HIDDEN` ~116)
- Create: migracja Alembic (autogenerate) w `backend/migrations/versions/`
- Test: `backend/tests/test_transit.py` (dopisać na końcu)

**Interfaces:**
- Produces: pola `customer_name: str`, `customer_address: str`, `customer_contact: str` (default `""`) na `Container`, w `ContainerCreate/Update/Out`. Task 2 konsumuje je przez `GET/PATCH /api/containers/{id}`.

- [ ] **Step 1: Failing testy** — dopisz do `backend/tests/test_transit.py` (użyj istniejących wzorców z tego pliku: `admin_headers` z conftest, `_make_user` jak w `test_purchasing_role.py:15` dla ról warehouse/customs):

```python
def test_transit_customer_fields_roundtrip(client, admin_headers):
    r = client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MSKU1234565", "company_code": "ACME", "is_transit": True,
        "customer_name": "ACME Sp. z o.o.", "customer_address": "ul. Prosta 1, Poznań",
        "customer_contact": "Jan Nowak, 600100200",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["customer_name"] == "ACME Sp. z o.o."
    cid = body["id"]
    r = client.patch(f"/api/containers/{cid}", headers=admin_headers,
                     json={"customer_name": "ACME 2"})
    assert r.status_code == 200
    assert r.json()["customer_name"] == "ACME 2"


def test_customer_fields_hidden_from_warehouse_and_customs(client, db_session):
    """Maskowanie na wyjściu (to_out) — wzorzec _WAREHOUSE_HIDDEN/_CUSTOMS_HIDDEN."""
    from app.models import Role, User
    from app.routers.containers import to_out
    headers = login(client)
    created = _create(client, headers, TRANSIT_NO, is_transit=True,
                      customer_name="ACME Sp. z o.o.",
                      customer_address="ul. Prosta 1, Poznań",
                      customer_contact="Jan Nowak, 600100200")
    container = db_session.get(Container, created["id"])
    for role in (Role.warehouse, Role.customs):
        out = to_out(container, User(login=f"mask-{role.value}",
                                     hashed_password="x", role=role))
        assert out.customer_name == ""
        assert out.customer_address == ""
        assert out.customer_contact == ""
```

Uwaga: pierwszy test dostosuj do lokalnego helpera `_create` (spółka po `company_id`,
jak w `test_transit.py:15-22`), nie `company_code`.

- [ ] **Step 2: Uruchom** — `pytest tests/test_transit.py -v` → FAIL (422/pole nieznane).

- [ ] **Step 3: Implementacja**

`models.py`, w `Container` pod `is_transit`:
```python
    # tranzyt: dane klienta docelowego (wpisywane ręcznie; maskowane dla warehouse/customs)
    customer_name: Mapped[str] = mapped_column(String, default="")
    customer_address: Mapped[str] = mapped_column(String, default="")
    customer_contact: Mapped[str] = mapped_column(String, default="")
```

`schemas.py` — `ContainerBase` (pod `is_transit`): `customer_name: str = ""`, `customer_address: str = ""`, `customer_contact: str = ""`; `ContainerUpdate`: te same jako `str | None = None`; `ContainerOut`: te same jako `str`.

`routers/containers.py` — do **obu** dictów `_WAREHOUSE_HIDDEN` i `_CUSTOMS_HIDDEN` dopisz:
```python
    "customer_name": "", "customer_address": "", "customer_contact": "",
```

Migracja (z `backend/`): `python -m alembic upgrade head && python -m alembic revision --autogenerate -m "container customer fields"` — sprawdź wygenerowany plik: 3× `op.add_column('containers', sa.Column(..., nullable=False, server_default=''))`; potem `python -m alembic upgrade head`.

- [ ] **Step 4: Testy zielone** — `pytest tests/test_transit.py -v` → PASS; potem pełne `pytest` (strażnicy ról i drift-guard w `test_deps.py` muszą przejść bez zmian — nowe pola nie zmieniają scope'u).

- [ ] **Step 5: Commit** — `git add backend && git commit -m "feat(tranzyt): dane klienta docelowego na kontenerze + maskowanie"`

---

### Task 2: Frontend — sekcja „Klient docelowy" w szczegółach kontenera

**Files:**
- Modify: `frontend/src/types.ts` (interfejs `Container`)
- Modify: `frontend/src/i18n.ts` (klucze w `pl`, `en`, `pt`)
- Modify: `frontend/src/pages/ContainerPage.tsx` (sekcja szczegółów, wzorzec `item(...)` ~linia 163)
- Test: `frontend/src/container.customer.dom.test.tsx` (nowy, na wzorcu `queue.planning.dom.test.tsx`)

**Interfaces:**
- Consumes: pola `customer_name/customer_address/customer_contact` z Task 1 (`GET/PATCH /api/containers/{id}` przez `api` z `frontend/src/api.ts`).

- [ ] **Step 1: Failing test** — `frontend/src/container.customer.dom.test.tsx`: render `ContainerPage` z zamockowanym kontenerem `{ is_transit: true, customer_name: 'ACME', ... }` (mock `api.get` jak w istniejących testach DOM); asercje: widoczny nagłówek `Klient docelowy` i tekst `ACME`; dla kontenera `is_transit: false` sekcji **nie ma**.

- [ ] **Step 2: Uruchom** — `npx vitest run container.customer` → FAIL.

- [ ] **Step 3: Implementacja**

`types.ts` — do `Container` dodaj: `customer_name: string; customer_address: string; customer_contact: string;`

`i18n.ts` — klucze (×3 języki): `transitCustomer` („Klient docelowy" / "Destination customer" / "Cliente de destino"), `customerName` („Nazwa"/"Name"/"Nome"), `customerAddress` („Adres dostawy"/"Delivery address"/"Morada de entrega"), `customerContact` („Kontakt"/"Contact"/"Contacto").

`ContainerPage.tsx` — pod istniejącym blokiem `item(...)` (za `notes`, ~172), renderowana tylko gdy `container.is_transit`:
```tsx
{container.is_transit && (
  <section className="panel">
    <h3>{t('transitCustomer')}</h3>
    {item(t('customerName'), container.customer_name)}
    {item(t('customerAddress'), container.customer_address)}
    {item(t('customerContact'), container.customer_contact)}
    {canEdit && (
      <button onClick={() => setEditCustomer(true)}>{t('edit')}</button>
    )}
  </section>
)}
```
Edycja: mały formularz inline (3× `<input>` + zapis `api.patch<Container>(`/api/containers/${container.id}`, {customer_name, customer_address, customer_contact})`, po sukcesie podmień stan kontenera). `canEdit` = rola admin/logistics — użyj tego samego warunku roli, który `ContainerPage` już stosuje dla innych akcji edycyjnych (jeśli brak — `['admin','logistics'].includes(user?.role ?? '')`). Klucz `edit` — jeśli już istnieje w i18n, użyj istniejącego.

- [ ] **Step 4: Testy zielone** — `npx vitest run` → PASS (całość, nie tylko nowy plik).

- [ ] **Step 5: Commit** — `git add frontend && git commit -m "feat(tranzyt): sekcja klienta docelowego w szczegółach kontenera"`

---

## Poza zakresem (świadomie)

- Ręczne DOSTARCZONY przez logistykę — już działa (containers.py:676).
- Rola purchasing — już w całości wdrożona.
- Kolumny klienta w kafelkach QueuePage — YAGNI, szczegóły wystarczą; dodać, gdy użytkownicy poproszą.
- Wyszukiwarka globalna i mapa — osobne plany (kolejne z tej gałęzi).
