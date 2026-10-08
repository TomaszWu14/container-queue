# Plan dostaw — data dostawy i cykl potwierdzeń ze spedycją — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kontener przechodzi jawny cykl planowania `PROPOZYCJA → WYSLANE → POTWIERDZONE`; dopiero potwierdzona przez spedycję data liczy się do dziennego limitu kolejki.

**Architecture:** Cała logika cyklu mieszka w nowym module domenowym `backend/app/planning.py` — routery, tracking i formularz tokenowy tylko go wołają. `Container.notify_date` pozostaje jedynym polem daty i kluczem kolejki; nowa kolumna `planning_status` mówi, ile ta data jest warta. Potwierdzenie ma dwie drogi wejścia (portal zalogowanej spedycji i publiczny link tokenowy), ale jedną funkcję domenową.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (`Mapped[...]`), Alembic, pytest; React + TypeScript + Vite, vitest + Testing Library.

## Global Constraints

- Spec źródłowy: `docs/superpowers/specs/2026-09-02-plan-dostaw-potwierdzenie-spedycji-design.md`.
- Domyślne wyprzedzenie dostawy: **`eta + 4 dni`** (stała `PLAN_LEAD_DAYS = 4`).
- Izolacja per-zasób **wyłącznie** przez `deps.py` (`check_container_access` / `get_scoped` / `scope_containers`) — nie powielać reguł dostępu w routerach (`CLAUDE.md`).
- Każda nowa kolumna w migracji **musi** trafić do dev-shimu `ensure_new_columns()` w `backend/app/main.py` — pilnuje tego `backend/tests/test_dev_schema_shim.py`.
- Przed dopisaniem migracji uruchomić `python -m alembic heads` — w repo zdarzyła się już kolizja identyfikatorów rewizji dająca `CycleDetected`.
- Zależności FastAPI w routerach: `Viewer`, `Editors`, `WarehouseOrEditors`, `AdminOnly` z `app/deps.py` (importowane w routerach jako aliasy lowercase, np. `from ..deps import Editors as editors`).
- Audyt zmian: `record_changes(db, obj, changes: dict, user, note="")` z `app/audit.py`; pojedyncze zdarzenie: `record(db, entity_type=..., entity_id=..., field=..., old_value=..., new_value=..., user=..., note=...)`.
- Wysyłka maili: `send_html_email(recipients, subject, html, reply_to="", channel="main")` z `app/notifications.py`.
- Testy backendu uruchamiane z katalogu `backend/`. Pełny suite trwa ~18 minut — w trakcie pracy uruchamiaj pojedyncze pliki.

---

## File Structure

**Backend — nowe:**
- `backend/app/planning.py` — moduł domenowy cyklu planowania. Jedyne miejsce z regułą zamrożenia, przejściami stanów i wyliczaniem alertu ETA. Bez zależności od FastAPI (czysta funkcja + `Session`), żeby dało się go testować i wołać z trackingu.
- `backend/migrations/versions/<rev>_container_planning.py` — migracja sześciu kolumn.
- `backend/tests/test_planning.py` — testy cyklu, reguły zamrożenia i limitu.
- `backend/tests/test_planning_confirm.py` — testy obu dróg potwierdzenia i izolacji spedytora.

**Backend — modyfikowane:**
- `backend/app/models.py` — enum `PlanningStatus` + sześć kolumn na `Container`.
- `backend/app/main.py` — dev-shim.
- `backend/app/schemas.py` — pola w `ContainerOut`, nowe schematy wejścia.
- `backend/app/routers/containers.py` — `used` w `/queue`, filtr `planning`, `plan/send`, `plan/confirm`, bloker w PATCH.
- `backend/app/routers/avizo.py` — data w formularzu tokenowym.
- `backend/app/tracking/service.py` — wołanie reguły zamrożenia po zmianie ETA.
- `backend/app/routers/admin.py` — serwerowa wysyłka zaproszenia.

**Frontend — modyfikowane:**
- `frontend/src/types.ts` — pola planowania na `Container`.
- `frontend/src/pages/queueRows.ts` — `splitByPlanning()`.
- `frontend/src/pages/QueuePage.tsx` — sekcje-nagłówki, zwijanie, bloker edycji.
- `frontend/src/pages/AvizoFormPage.tsx` — pole daty.
- `frontend/src/pages/ForwardingPage.tsx` — zakładka „Do potwierdzenia".
- `frontend/src/i18n.ts` — teksty.
- `frontend/src/queue.planning.dom.test.tsx` — nowy test DOM.

**Kolejność zadań:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10. Zadania 1-2 są fundamentem; 3-7 to backend cyklu; 8-9 to frontend; 10 (zaproszenia) jest niezależne i może iść równolegle.

---

### Task 1: Model, enum i migracja

**Files:**
- Modify: `backend/app/models.py` (enum obok `ContainerStatus`, ~linia 69; kolumny w `Container`, ~linia 379)
- Modify: `backend/app/main.py` (słownik `ddl` w `ensure_new_columns()`, ~linia 387)
- Create: `backend/migrations/versions/b8c9d0e1f2a3_container_planning.py`
- Test: `backend/tests/test_planning.py`

**Interfaces:**
- Consumes: nic (pierwsze zadanie).
- Produces: `PlanningStatus` (enum: `PROPOZYCJA`, `WYSLANE`, `POTWIERDZONE`) oraz pola `Container.planning_status`, `.notify_date_manual`, `.planning_sent_at`, `.planning_confirmed_at`, `.planning_confirmed_by_id`, `.planning_eta_at_send`.

- [ ] **Step 1: Sprawdź stan migracji przed dopisaniem nowej**

Run: `cd backend && python -m alembic heads`
Expected: dokładnie jedna linia zakończona `(head)`. Zapisz ten identyfikator — będzie `down_revision`. W chwili pisania planu jest to `a2c3d4e5f6b7`. Jeśli poleci `CycleDetected`, napraw kolizję rewizji **zanim** ruszysz dalej.

- [ ] **Step 2: Napisz failing test**

Utwórz `backend/tests/test_planning.py`:

```python
"""Cykl planowania dostawy: PROPOZYCJA -> WYSLANE -> POTWIERDZONE."""
from app.models import Container, PlanningStatus
from tests.conftest import login


def _create(client, headers, container_no, **extra):
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    payload = {"container_no": container_no, "company_id": company_id,
               "status": "ZAPOWIEDZIANY", **extra}
    response = client.post("/api/containers", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_new_container_starts_as_proposal(client):
    headers = login(client)
    created = _create(client, headers, "PLAN0000001")
    assert created["planning_status"] == "PROPOZYCJA"
    assert created["notify_date_manual"] is False
```

- [ ] **Step 3: Uruchom test — ma nie przejść**

Run: `cd backend && python -m pytest tests/test_planning.py -q`
Expected: FAIL — `ImportError: cannot import name 'PlanningStatus'`.

- [ ] **Step 4: Dodaj enum do `models.py`**

Obok pozostałych enumów statusów (za `ContainerStatus`, ~linia 77):

```python
class PlanningStatus(str, enum.Enum):
    """Ile warta jest data w `Container.notify_date`.

    PROPOZYCJA   — nasza zgadywanka (eta + 4 dni); ETA z API może ją jeszcze przesunąć.
    WYSLANE      — poszła do spedycji, czeka na odpowiedź; data zamrożona.
    POTWIERDZONE — spedycja uzgodniła; tylko te liczą się do dziennego limitu.
    """
    PROPOZYCJA = "PROPOZYCJA"
    WYSLANE = "WYSLANE"
    POTWIERDZONE = "POTWIERDZONE"
```

- [ ] **Step 5: Dodaj kolumny do `Container`**

Bezpośrednio pod `proposed_delivery_date` (~linia 379):

```python
    # --- cykl planowania dostawy (spec 2026-09-02) ---
    # notify_date pozostaje JEDYNYM polem daty i kluczem kolejki; poniższe mówią,
    # ile ta data jest warta i czy wolno ją jeszcze przeliczać z ETA.
    planning_status: Mapped[PlanningStatus] = mapped_column(
        Enum(PlanningStatus), default=PlanningStatus.PROPOZYCJA,
        server_default="PROPOZYCJA", nullable=False, index=True)
    # człowiek wpisał datę ręcznie — ETA z API już jej nie nadpisuje, nawet w PROPOZYCJI
    notify_date_manual: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_false(), nullable=False)
    planning_sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    planning_confirmed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # NULL gdy potwierdzenie przyszło publicznym linkiem tokenowym (brak zalogowanego usera)
    planning_confirmed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True)
    # zdjęcie ETA w chwili zamrożenia; alert "ETA przesunięta" liczymy w locie z różnicy,
    # zamiast trzymać flagę, która rozjeżdżałaby się przy każdej zmianie ETA
    planning_eta_at_send: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
```

W imporcie SQLAlchemy na górze pliku dopisz `false as sa_false` do listy importowanej z `sqlalchemy` (obok `Boolean`, `Date`, `DateTime`, `Enum`, `ForeignKey`).

- [ ] **Step 6: Napisz migrację**

Utwórz `backend/migrations/versions/b8c9d0e1f2a3_container_planning.py`:

```python
"""cykl planowania dostawy: planning_status + pola towarzyszące

Revision ID: b8c9d0e1f2a3
Revises: a2c3d4e5f6b7
Create Date: 2026-09-02 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a2c3d4e5f6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('containers', sa.Column(
        'planning_status', sa.Enum('PROPOZYCJA', 'WYSLANE', 'POTWIERDZONE',
                                   name='planningstatus'),
        nullable=False, server_default='PROPOZYCJA'))
    op.create_index('ix_containers_planning_status', 'containers', ['planning_status'])
    op.add_column('containers', sa.Column('notify_date_manual', sa.Boolean(),
                                          nullable=False, server_default=sa.false()))
    op.add_column('containers', sa.Column('planning_sent_at', sa.DateTime(), nullable=True))
    op.add_column('containers', sa.Column('planning_confirmed_at', sa.DateTime(), nullable=True))
    op.add_column('containers', sa.Column('planning_confirmed_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_containers_planning_confirmed_by', 'containers', 'users',
                          ['planning_confirmed_by_id'], ['id'])
    op.add_column('containers', sa.Column('planning_eta_at_send', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_constraint('fk_containers_planning_confirmed_by', 'containers', type_='foreignkey')
    op.drop_column('containers', 'planning_eta_at_send')
    op.drop_column('containers', 'planning_confirmed_by_id')
    op.drop_column('containers', 'planning_confirmed_at')
    op.drop_column('containers', 'planning_sent_at')
    op.drop_column('containers', 'notify_date_manual')
    op.drop_index('ix_containers_planning_status', table_name='containers')
    op.drop_column('containers', 'planning_status')
```

- [ ] **Step 7: Dopisz kolumny do dev-shimu**

W `backend/app/main.py`, w słowniku `ddl` funkcji `ensure_new_columns()` (obok `'is_transit'`):

```python
        'planning_status': "VARCHAR(20) DEFAULT 'PROPOZYCJA' NOT NULL",
        'notify_date_manual': "BOOLEAN DEFAULT 0 NOT NULL",
        'planning_sent_at': "DATETIME",
        'planning_confirmed_at': "DATETIME",
        'planning_confirmed_by_id': "INTEGER",
        'planning_eta_at_send': "DATE",
```

- [ ] **Step 8: Dodaj pola do `ContainerOut`**

W `backend/app/schemas.py`, w klasie `ContainerOut` (obok `is_transit`, ~linia 517):

```python
    planning_status: str = "PROPOZYCJA"
    notify_date_manual: bool = False
    planning_sent_at: datetime.datetime | None = None
    planning_confirmed_at: datetime.datetime | None = None
```

- [ ] **Step 9: Uruchom testy**

Run: `cd backend && python -m pytest tests/test_planning.py tests/test_dev_schema_shim.py -q`
Expected: PASS (2+ testy).

Run: `cd backend && python -m alembic heads`
Expected: `b8c9d0e1f2a3 (head)` — jedna linia.

- [ ] **Step 10: Commit**

```bash
git add backend/app/models.py backend/app/main.py backend/app/schemas.py \
        backend/migrations/versions/b8c9d0e1f2a3_container_planning.py \
        backend/tests/test_planning.py
git commit -m "feat(plan): model cyklu planowania dostawy (planning_status + migracja)"
```

---

### Task 2: Moduł domenowy `planning.py` — reguła zamrożenia

**Files:**
- Create: `backend/app/planning.py`
- Modify: `backend/tests/test_planning.py`

**Interfaces:**
- Consumes: `PlanningStatus`, pola `Container` z Task 1.
- Produces:
  - `PLAN_LEAD_DAYS: int = 4`
  - `def proposed_date(eta: datetime.date) -> datetime.date`
  - `def can_autoshift(container: Container) -> bool`
  - `def apply_eta(db: Session, container: Container, note: str = "") -> bool`
  - `def eta_shift_days(container: Container) -> int | None`

- [ ] **Step 1: Napisz failing testy reguły zamrożenia**

Dopisz do `backend/tests/test_planning.py`:

```python
import datetime

from app.planning import PLAN_LEAD_DAYS, apply_eta, can_autoshift, eta_shift_days, proposed_date


def test_proposed_date_is_eta_plus_lead():
    assert proposed_date(datetime.date(2026, 9, 1)) == datetime.date(2026, 9, 1 + PLAN_LEAD_DAYS)


def test_autoshift_allowed_only_for_untouched_proposal():
    container = Container(planning_status=PlanningStatus.PROPOZYCJA, notify_date_manual=False)
    assert can_autoshift(container) is True

    container.notify_date_manual = True
    assert can_autoshift(container) is False, "ręczna edycja zamraża datę"

    container.notify_date_manual = False
    container.planning_status = PlanningStatus.WYSLANE
    assert can_autoshift(container) is False, "wysłane do spedycji zamraża datę"

    container.planning_status = PlanningStatus.POTWIERDZONE
    assert can_autoshift(container) is False


def test_eta_shift_is_none_without_snapshot():
    container = Container(eta=datetime.date(2026, 9, 10), planning_eta_at_send=None)
    assert eta_shift_days(container) is None


def test_eta_shift_counts_days_from_snapshot():
    container = Container(eta=datetime.date(2026, 9, 12),
                          planning_eta_at_send=datetime.date(2026, 9, 10))
    assert eta_shift_days(container) == 2
```

- [ ] **Step 2: Uruchom testy — mają nie przejść**

Run: `cd backend && python -m pytest tests/test_planning.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.planning'`.

- [ ] **Step 3: Napisz moduł**

Utwórz `backend/app/planning.py`:

```python
"""Cykl planowania dostawy — jedyne miejsce z regułą zamrożenia daty.

`Container.notify_date` jest jednocześnie planowaną datą dostawy i kluczem dnia
w kolejce. Żeby ETA z API nie przestawiała w tle terminu uzgodnionego ze spedycją,
automatyczne przeliczanie działa wyłącznie na nietkniętej propozycji. Wszędzie
indziej zmiana ETA jedynie podnosi alert — decyzję o przeplanowaniu podejmuje człowiek.
"""
import datetime

from sqlalchemy.orm import Session

from .audit import record_changes
from .models import Container, PlanningStatus

# domyślne wyprzedzenie: rozładunek planujemy 4 dni po przypłynięciu
PLAN_LEAD_DAYS = 4


def proposed_date(eta: datetime.date) -> datetime.date:
    """Domyślna data dostawy wyliczona z ETA."""
    return eta + datetime.timedelta(days=PLAN_LEAD_DAYS)


def can_autoshift(container: Container) -> bool:
    """Czy ETA z API może jeszcze przesunąć `notify_date`.

    Tylko nietknięta propozycja. Wysyłka do spedycji i ręczna edycja zamrażają datę.
    """
    return (container.planning_status == PlanningStatus.PROPOZYCJA
            and not container.notify_date_manual)


def apply_eta(db: Session, container: Container, note: str = "") -> bool:
    """Przelicza `notify_date` z aktualnej ETA, jeśli reguła zamrożenia na to pozwala.

    Zwraca True, gdy data faktycznie się zmieniła. Zapis idzie przez `record_changes`,
    więc przesunięcie zostaje w audycie. Commit należy do wołającego.
    """
    if not container.eta or not can_autoshift(container):
        return False
    new_date = proposed_date(container.eta)
    if container.notify_date == new_date:
        return False
    record_changes(db, container, {"notify_date": new_date}, user=None,
                   note=note or "przeliczenie z ETA (propozycja)")
    return True


def eta_shift_days(container: Container) -> int | None:
    """O ile dni ETA przesunęła się od zamrożenia planu. None = brak zdjęcia ETA.

    Dodatnia wartość = statek spóźniony względem stanu z chwili wysyłki do spedycji.
    """
    if not container.planning_eta_at_send or not container.eta:
        return None
    return (container.eta - container.planning_eta_at_send).days
```

- [ ] **Step 4: Uruchom testy**

Run: `cd backend && python -m pytest tests/test_planning.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/planning.py backend/tests/test_planning.py
git commit -m "feat(plan): moduł domenowy planning.py z regułą zamrożenia daty"
```

---

### Task 3: Podpięcie reguły do trackingu i tworzenia kontenera

**Files:**
- Modify: `backend/app/tracking/service.py:42-56`
- Modify: `backend/app/routers/containers.py` (tworzenie kontenera — funkcja `create_container`)
- Test: `backend/tests/test_planning.py`

**Interfaces:**
- Consumes: `apply_eta`, `proposed_date` z Task 2.
- Produces: nic nowego — istniejące ścieżki zaczynają ustawiać `notify_date`.

- [ ] **Step 1: Napisz failing test**

Dopisz do `backend/tests/test_planning.py`:

```python
def test_creating_container_with_eta_sets_proposal_date(client):
    headers = login(client)
    created = _create(client, headers, "PLAN0000002", eta="2026-10-01")
    assert created["notify_date"] == "2026-10-05", "eta + 4 dni"
    assert created["planning_status"] == "PROPOZYCJA"


def test_manual_notify_date_marks_container_as_manual(client):
    headers = login(client)
    created = _create(client, headers, "PLAN0000003", eta="2026-10-01")
    response = client.patch(f"/api/containers/{created['id']}",
                            json={"notify_date": "2026-10-09"}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["notify_date_manual"] is True
```

- [ ] **Step 2: Uruchom testy — mają nie przejść**

Run: `cd backend && python -m pytest tests/test_planning.py -q`
Expected: FAIL — `notify_date` jest `None` zamiast `"2026-10-05"`.

- [ ] **Step 3: Ustaw propozycję przy tworzeniu kontenera**

W `backend/app/routers/containers.py`, w funkcji `create_container`, po utworzeniu obiektu a przed `db.commit()`:

```python
    # brak jawnej daty rozładunku + znana ETA => wstępna propozycja (eta + 4 dni)
    if container.eta and not container.notify_date:
        container.notify_date = proposed_date(container.eta)
```

Import na górze pliku: `from ..planning import proposed_date`.

- [ ] **Step 4: Oznacz ręczną edycję daty w PATCH**

W `backend/app/routers/containers.py`, w `update_container`, po `changes = body.model_dump(exclude_unset=True)` i `note = changes.pop("change_note", "")`:

```python
    # ręczne wpisanie daty zamraża ją przed automatem ETA (patrz app/planning.py)
    if "notify_date" in changes and changes["notify_date"] != container.notify_date:
        changes["notify_date_manual"] = True
```

Uwaga: ten fragment musi stać **przed** `record_changes(...)`, żeby flaga trafiła do tego samego zapisu.

- [ ] **Step 5: Podepnij regułę do trackingu**

W `backend/app/tracking/service.py`, bezpośrednio po `container.eta = result.eta` (linia ~46):

```python
        # ETA przesunęła plan tylko wtedy, gdy nikt jeszcze planu nie tknął
        apply_eta(db, container, note="tracking: nowa ETA")
```

Import na górze pliku: `from ..planning import apply_eta`.

- [ ] **Step 6: Uruchom testy**

Run: `cd backend && python -m pytest tests/test_planning.py tests/test_tracking.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/containers.py backend/app/tracking/service.py \
        backend/tests/test_planning.py
git commit -m "feat(plan): propozycja eta+4 przy tworzeniu i przeliczanie z trackingu"
```

---

### Task 4: Limit dzienny liczy tylko potwierdzone + filtr w `/api/queue`

**Files:**
- Modify: `backend/app/routers/containers.py:775-830` (`queue_view`)
- Test: `backend/tests/test_planning.py`

**Interfaces:**
- Consumes: `PlanningStatus` z Task 1.
- Produces: parametr zapytania `planning: str | None` w `GET /api/queue`.

- [ ] **Step 1: Napisz failing testy**

Dopisz do `backend/tests/test_planning.py`:

```python
def test_proposal_does_not_count_towards_daily_limit(client):
    headers = login(client)
    _create(client, headers, "PLAN0000010", notify_date="2026-11-02")
    days = client.get("/api/queue?date_from=2026-11-02&date_to=2026-11-02",
                      headers=headers).json()
    assert days[0]["used"] == 0, "propozycja jest widoczna, ale nie zajmuje slotu"
    assert len(days[0]["containers"]) == 1


def test_confirmed_container_counts_towards_daily_limit(client, db_session):
    headers = login(client)
    created = _create(client, headers, "PLAN0000011", notify_date="2026-11-03")
    container = db_session.get(Container, created["id"])
    container.planning_status = PlanningStatus.POTWIERDZONE
    db_session.commit()
    days = client.get("/api/queue?date_from=2026-11-03&date_to=2026-11-03",
                      headers=headers).json()
    assert days[0]["used"] == 1


def test_queue_filters_by_planning_status(client, db_session):
    headers = login(client)
    created = _create(client, headers, "PLAN0000012", notify_date="2026-11-04")
    _create(client, headers, "PLAN0000013", notify_date="2026-11-04")
    container = db_session.get(Container, created["id"])
    container.planning_status = PlanningStatus.POTWIERDZONE
    db_session.commit()
    days = client.get("/api/queue?date_from=2026-11-04&date_to=2026-11-04"
                      "&planning=POTWIERDZONE", headers=headers).json()
    assert [c["container_no"] for c in days[0]["containers"]] == ["PLAN0000012"]
```

Jeśli w `tests/conftest.py` nie ma fixture'u `db_session` dającego `Session` do tej samej bazy co `client`, dodaj go tam — bez niego nie da się ustawić stanu, którego API jeszcze nie wystawia.

- [ ] **Step 2: Uruchom testy — mają nie przejść**

Run: `cd backend && python -m pytest tests/test_planning.py -q`
Expected: FAIL — `used == 1` zamiast `0`.

- [ ] **Step 3: Zmień licznik i dodaj filtr**

W `backend/app/routers/containers.py`, w sygnaturze `queue_view` dopisz parametr po `transit`:

```python
    planning: str | None = None,
```

Za blokiem `if transit is not None:`:

```python
    # filtr sekcji planowania (kolejka wysyła PROPOZYCJA / WYSLANE / POTWIERDZONE)
    if planning is not None:
        query = query.where(Container.planning_status == PlanningStatus(planning))
```

Licznik `used` (linia ~823) zastąp:

```python
        # do limitu liczymy wyłącznie terminy uzgodnione ze spedycją — propozycja
        # i wysyłka czekająca na odpowiedź nie rezerwują slotu rozładunkowego
        used = sum(1 for c in items
                   if c.status not in Container.FINISHED and not c.is_transit
                   and c.planning_status == PlanningStatus.POTWIERDZONE)
```

Dopisz `PlanningStatus` do importu z `..models`.

- [ ] **Step 4: Uruchom testy**

Run: `cd backend && python -m pytest tests/test_planning.py tests/test_transit.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/containers.py backend/tests/test_planning.py
git commit -m "feat(plan): limit dzienny liczy tylko potwierdzone + filtr planning w /api/queue"
```

---

### Task 5: Wysyłka planu do spedycji

**Files:**
- Modify: `backend/app/planning.py`
- Modify: `backend/app/routers/containers.py`
- Test: `backend/tests/test_planning_confirm.py`

**Interfaces:**
- Consumes: `PlanningStatus`, `can_autoshift` z Task 1-2.
- Produces:
  - `def send_to_forwarder(db: Session, container: Container, user: User) -> None` w `planning.py`
  - `POST /api/containers/plan/send`, body `{"container_ids": [int]}`, odpowiedź `{"sent": int, "no_forwarder": [str], "skipped": [str]}`

- [ ] **Step 1: Napisz failing testy**

Utwórz `backend/tests/test_planning_confirm.py`:

```python
"""Wysyłka planu do spedycji i potwierdzanie daty (portal + token)."""
from app.models import Container, PlanningStatus
from tests.conftest import login


def _create(client, headers, container_no, **extra):
    companies = client.get("/api/companies", headers=headers).json()
    company_id = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    payload = {"container_no": container_no, "company_id": company_id,
               "status": "ZAPOWIEDZIANY", **extra}
    response = client.post("/api/containers", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _forwarder_id(client, headers):
    forwarders = client.get("/api/forwarders", headers=headers).json()
    assert forwarders, "brak spedytorów w danych testowych"
    return forwarders[0]["id"]


def test_send_freezes_date_and_snapshots_eta(client, db_session):
    headers = login(client)
    created = _create(client, headers, "PLAN0000020", eta="2026-10-01",
                      forwarder_id=_forwarder_id(client, headers))
    response = client.post("/api/containers/plan/send",
                           json={"container_ids": [created["id"]]}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["sent"] == 1

    container = db_session.get(Container, created["id"])
    assert container.planning_status == PlanningStatus.WYSLANE
    assert container.planning_sent_at is not None
    assert container.planning_eta_at_send == container.eta


def test_send_reports_container_without_forwarder(client):
    headers = login(client)
    created = _create(client, headers, "PLAN0000021", eta="2026-10-01")
    response = client.post("/api/containers/plan/send",
                           json={"container_ids": [created["id"]]}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["sent"] == 0
    assert response.json()["no_forwarder"] == ["PLAN0000021"]


def test_eta_change_after_send_does_not_move_date(client, db_session):
    from app.planning import apply_eta
    import datetime

    headers = login(client)
    created = _create(client, headers, "PLAN0000022", eta="2026-10-01",
                      forwarder_id=_forwarder_id(client, headers))
    client.post("/api/containers/plan/send",
                json={"container_ids": [created["id"]]}, headers=headers)

    container = db_session.get(Container, created["id"])
    frozen = container.notify_date
    container.eta = datetime.date(2026, 10, 8)
    assert apply_eta(db_session, container) is False
    assert container.notify_date == frozen, "wysłany plan nie może się sam przesunąć"
```

- [ ] **Step 2: Uruchom testy — mają nie przejść**

Run: `cd backend && python -m pytest tests/test_planning_confirm.py -q`
Expected: FAIL — 404 na `/api/containers/plan/send`.

- [ ] **Step 3: Dodaj funkcję domenową**

Dopisz do `backend/app/planning.py`:

```python
def send_to_forwarder(db: Session, container: Container, user) -> None:
    """Zamraża plan i oznacza go jako wysłany do spedycji.

    Zdjęcie ETA (`planning_eta_at_send`) jest punktem odniesienia dla alertu
    „ETA przesunięta o X dni". Commit należy do wołającego.
    """
    container.planning_status = PlanningStatus.WYSLANE
    container.planning_sent_at = utcnow()
    container.planning_eta_at_send = container.eta
    record(db, entity_type="containers", entity_id=container.id, field="planning_status",
           old_value=None, new_value=PlanningStatus.WYSLANE.value, user=user,
           note="wysłano plan do spedycji")
```

Rozszerz importy na górze `planning.py`:

```python
from .audit import record, record_changes
from .models import Container, PlanningStatus
from .utils import utcnow
```

(Jeśli `utcnow` mieszka w `app/models.py`, importuj je stamtąd — sprawdź `grep -n "def utcnow" backend/app/*.py` i użyj właściwej ścieżki.)

- [ ] **Step 4: Dodaj endpoint**

W `backend/app/routers/containers.py`, obok pozostałych endpointów kontenerów:

```python
class PlanSendIn(BaseModel):
    container_ids: list[int] = Field(min_length=1)


@router.post("/containers/plan/send")
def send_plan(body: PlanSendIn, db: Session = Depends(get_db), user: User = editors):
    """Wysyła propozycje dat do spedycji — zamraża je i oznacza jako oczekujące."""
    containers = db.scalars(select(Container)
                            .options(selectinload(Container.forwarder))
                            .where(Container.id.in_(body.container_ids))).all()
    if not containers:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono kontenerów.")
    for c in containers:
        check_container_access(user, c)

    sent, no_forwarder, skipped = 0, [], []
    for c in containers:
        if not c.forwarder_id:
            # bez spedytora nie ma komu wysłać — zgłaszamy zamiast po cichu pomijać
            no_forwarder.append(c.container_no)
            continue
        if c.planning_status == PlanningStatus.POTWIERDZONE:
            skipped.append(c.container_no)
            continue
        send_to_forwarder(db, c, user)
        sent += 1
    db.commit()
    return {"sent": sent, "no_forwarder": no_forwarder, "skipped": skipped}
```

Import: `from ..planning import proposed_date, send_to_forwarder`.

Uwaga na kolejność tras: `plan/send` musi być zarejestrowane **przed** ewentualną trasą `/containers/{container_id}`, inaczej FastAPI spróbuje sparsować `"plan"` jako `container_id`.

- [ ] **Step 5: Uruchom testy**

Run: `cd backend && python -m pytest tests/test_planning_confirm.py -q`
Expected: PASS (3 testy).

- [ ] **Step 6: Commit**

```bash
git add backend/app/planning.py backend/app/routers/containers.py \
        backend/tests/test_planning_confirm.py
git commit -m "feat(plan): endpoint wysyłki planu do spedycji (zamrożenie + zdjęcie ETA)"
```

---

### Task 6: Potwierdzanie daty — funkcja domenowa i portal spedycji

**Files:**
- Modify: `backend/app/planning.py`
- Modify: `backend/app/routers/containers.py`
- Test: `backend/tests/test_planning_confirm.py`

**Interfaces:**
- Consumes: `send_to_forwarder`, `PlanningStatus`.
- Produces:
  - `def confirm_plan(db: Session, container: Container, day: datetime.date, confirmed_by) -> None`
  - `def reset_plan(db: Session, container: Container, user, note: str) -> None`
  - `POST /api/containers/{id}/plan/confirm`, body `{"delivery_date": "YYYY-MM-DD"}`
  - `GET /api/containers/plan/pending` — lista dla portalu spedycji

- [ ] **Step 1: Napisz failing testy**

Dopisz do `backend/tests/test_planning_confirm.py`:

```python
def test_confirm_sets_status_and_date(client, db_session):
    headers = login(client)
    created = _create(client, headers, "PLAN0000030", eta="2026-10-01",
                      forwarder_id=_forwarder_id(client, headers))
    client.post("/api/containers/plan/send",
                json={"container_ids": [created["id"]]}, headers=headers)
    response = client.post(f"/api/containers/{created['id']}/plan/confirm",
                           json={"delivery_date": "2026-10-07"}, headers=headers)
    assert response.status_code == 200, response.text

    container = db_session.get(Container, created["id"])
    assert container.planning_status == PlanningStatus.POTWIERDZONE
    assert container.notify_date.isoformat() == "2026-10-07"
    assert container.planning_confirmed_at is not None
    assert container.planning_confirmed_by_id is not None


def test_changing_date_of_confirmed_container_resets_to_proposal(client, db_session):
    headers = login(client)
    created = _create(client, headers, "PLAN0000031", eta="2026-10-01",
                      forwarder_id=_forwarder_id(client, headers))
    client.post("/api/containers/plan/send",
                json={"container_ids": [created["id"]]}, headers=headers)
    client.post(f"/api/containers/{created['id']}/plan/confirm",
                json={"delivery_date": "2026-10-07"}, headers=headers)

    response = client.patch(f"/api/containers/{created['id']}",
                            json={"notify_date": "2026-10-09"}, headers=headers)
    assert response.status_code == 200, response.text
    container = db_session.get(Container, created["id"])
    assert container.planning_status == PlanningStatus.PROPOZYCJA, \
        "data, której spedycja nie widziała, nie może uchodzić za uzgodnioną"
    assert container.planning_confirmed_at is None
    assert container.planning_confirmed_by_id is None
```

- [ ] **Step 2: Uruchom testy — mają nie przejść**

Run: `cd backend && python -m pytest tests/test_planning_confirm.py -q`
Expected: FAIL — 404 na `plan/confirm`.

- [ ] **Step 3: Dodaj funkcje domenowe**

Dopisz do `backend/app/planning.py`:

```python
def confirm_plan(db: Session, container: Container, day: datetime.date, confirmed_by) -> None:
    """Spedycja uzgodniła datę. `confirmed_by` = None przy potwierdzeniu tokenem.

    Wołane z obu dróg wejścia (portal i publiczny formularz), żeby reguła istniała
    w jednym miejscu. Commit należy do wołającego.
    """
    changes = {"planning_status": PlanningStatus.POTWIERDZONE}
    if container.notify_date != day:
        changes["notify_date"] = day
    record_changes(db, container, changes, user=confirmed_by,
                   note="potwierdzenie planu przez spedycję")
    container.planning_confirmed_at = utcnow()
    container.planning_confirmed_by_id = confirmed_by.id if confirmed_by else None


def reset_plan(db: Session, container: Container, user, note: str) -> None:
    """Cofa plan do propozycji i czyści ślad potwierdzenia.

    Wołane, gdy ktoś zmienia datę uzgodnioną ze spedycją: inaczej rekord dalej
    udawałby uzgodniony i wciąż zajmowałby slot w dziennym limicie.
    """
    record_changes(db, container, {"planning_status": PlanningStatus.PROPOZYCJA},
                   user=user, note=note)
    container.planning_confirmed_at = None
    container.planning_confirmed_by_id = None
    container.planning_sent_at = None
    container.planning_eta_at_send = None
```

- [ ] **Step 4: Dodaj endpointy**

W `backend/app/routers/containers.py`:

```python
class PlanConfirmIn(BaseModel):
    delivery_date: datetime.date


@router.post("/containers/{container_id}/plan/confirm")
def confirm_plan_endpoint(container_id: int, body: PlanConfirmIn,
                          db: Session = Depends(get_db), user: User = viewer):
    """Potwierdzenie daty przez zalogowaną spedycję (portal).

    Izolacja: get_scoped odrzuci cudzy kontener (404) — bez własnych reguł w routerze.
    """
    container = get_scoped(db, Container, container_id, user)
    confirm_plan(db, container, body.delivery_date, confirmed_by=user)
    db.commit()
    return to_out(container, user)


@router.get("/containers/plan/pending", response_model=list[ContainerOut])
def pending_plan(db: Session = Depends(get_db), user: User = viewer):
    """Kontenery czekające na potwierdzenie daty — lista dla modułu spedycji."""
    query = (select(Container).options(*_LOAD)
             .where(Container.planning_status == PlanningStatus.WYSLANE)
             .order_by(Container.notify_date, Container.id))
    return [to_out(c, user) for c in db.scalars(scope_containers(query, user)).all()]
```

Import: `from ..planning import confirm_plan, proposed_date, reset_plan, send_to_forwarder`.

Kolejność tras: `containers/plan/pending` musi stać **przed** `containers/{container_id}`.

- [ ] **Step 5: Podepnij cofanie w PATCH**

W `update_container`, rozszerz blok dodany w Task 3 Step 4:

```python
    # ręczne wpisanie daty zamraża ją przed automatem ETA (patrz app/planning.py)
    reset_needed = False
    if "notify_date" in changes and changes["notify_date"] != container.notify_date:
        changes["notify_date_manual"] = True
        # data uzgodniona ze spedycją zmieniona u nas => plan przestaje być uzgodniony
        reset_needed = container.planning_status == PlanningStatus.POTWIERDZONE
```

Po `record_changes(...)`, przed `db.commit()`:

```python
    if reset_needed:
        reset_plan(db, container, user, note="zmiana daty po potwierdzeniu spedycji")
```

- [ ] **Step 6: Uruchom testy**

Run: `cd backend && python -m pytest tests/test_planning_confirm.py tests/test_planning.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/planning.py backend/app/routers/containers.py \
        backend/tests/test_planning_confirm.py
git commit -m "feat(plan): potwierdzanie daty przez portal spedycji + cofanie po zmianie daty"
```

---

### Task 7: Izolacja spedytora i potwierdzanie linkiem tokenowym

**Files:**
- Modify: `backend/app/routers/avizo.py:218-276`
- Test: `backend/tests/test_planning_confirm.py`

**Interfaces:**
- Consumes: `confirm_plan` z Task 6.
- Produces: pole `delivery_date` w `AvizoDriverItemIn` i w odpowiedzi `GET /api/avizo/{token}`.

- [ ] **Step 1: Napisz failing testy**

Dopisz do `backend/tests/test_planning_confirm.py`:

```python
def test_forwarder_cannot_confirm_foreign_container(client, db_session):
    """Spedytor przypisany do innej firmy nie widzi cudzego kontenera (404 z get_scoped)."""
    headers = login(client)
    created = _create(client, headers, "PLAN0000040", eta="2026-10-01",
                      forwarder_id=_forwarder_id(client, headers))
    container = db_session.get(Container, created["id"])
    container.forwarder_id = None          # kontener bez przypisanej spedycji
    db_session.commit()

    forwarder_headers = login(client, role="forwarder")
    response = client.post(f"/api/containers/{created['id']}/plan/confirm",
                           json={"delivery_date": "2026-10-07"}, headers=forwarder_headers)
    assert response.status_code in (403, 404), response.text
```

Jeśli `tests/conftest.py:login` nie przyjmuje jeszcze roli, rozszerz go tak, by umiał zalogować użytkownika o zadanej roli — konto spedytora z ustawionym `forwarder_id` jest potrzebne także w kolejnych zadaniach.

- [ ] **Step 2: Uruchom test — ma nie przejść**

Run: `cd backend && python -m pytest tests/test_planning_confirm.py -q`
Expected: FAIL — `login()` nie przyjmuje argumentu `role`.

- [ ] **Step 3: Dodaj datę do publicznego formularza**

W `backend/app/routers/avizo.py`, w `AvizoDriverItemIn`:

```python
    delivery_date: datetime.date | None = None   # data uzgodniona przez spedycję
```

W `get_avizo`, w słowniku pozycji, obok `notify_date`:

```python
            "planning_status": item.container.planning_status.value,
```

W `confirm_avizo`, wewnątrz pętli, po `confirmed_count += 1`:

```python
        # spedycja akceptuje naszą datę albo wpisuje własną — obie drogi kończą
        # się tą samą funkcją domenową co potwierdzenie w portalu
        day = entry.delivery_date or item.container.notify_date
        if day:
            confirm_plan(db, item.container, day, confirmed_by=None)
```

Import: `from ..planning import confirm_plan`.

- [ ] **Step 4: Uruchom testy**

Run: `cd backend && python -m pytest tests/test_planning_confirm.py tests/test_avizo.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/avizo.py backend/tests/conftest.py \
        backend/tests/test_planning_confirm.py
git commit -m "feat(plan): potwierdzanie daty przez publiczny formularz awizacji"
```

---

### Task 8: Kolejka — sekcje planowania i bloker edycji

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/pages/queueRows.ts`
- Modify: `frontend/src/pages/QueuePage.tsx:1033-1090`
- Modify: `frontend/src/i18n.ts`
- Test: `frontend/src/queue.planning.dom.test.tsx`

**Interfaces:**
- Consumes: pola `planning_status`, `planning_sent_at` z `ContainerOut` (Task 1).
- Produces: `export function splitByPlanning(items: Container[]): PlanningGroup[]`, gdzie `PlanningGroup = { status: 'POTWIERDZONE' | 'WYSLANE' | 'PROPOZYCJA'; items: Container[] }`.

- [ ] **Step 1: Napisz failing test**

Utwórz `frontend/src/queue.planning.dom.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { splitByPlanning } from './pages/queueRows'
import type { Container } from './types'

const make = (id: number, planning_status: string) =>
  ({ id, container_no: `C${id}`, planning_status } as unknown as Container)

describe('splitByPlanning', () => {
  it('zwraca sekcje w kolejności: potwierdzone, wysłane, propozycje', () => {
    const groups = splitByPlanning([
      make(1, 'PROPOZYCJA'), make(2, 'POTWIERDZONE'), make(3, 'WYSLANE'),
    ])
    expect(groups.map(g => g.status)).toEqual(['POTWIERDZONE', 'WYSLANE', 'PROPOZYCJA'])
    expect(groups[0].items.map(c => c.id)).toEqual([2])
  })

  it('pomija puste sekcje', () => {
    const groups = splitByPlanning([make(1, 'PROPOZYCJA')])
    expect(groups.map(g => g.status)).toEqual(['PROPOZYCJA'])
  })
})
```

- [ ] **Step 2: Uruchom test — ma nie przejść**

Run: `cd frontend && npx vitest run src/queue.planning.dom.test.tsx`
Expected: FAIL — `splitByPlanning is not a function`.

- [ ] **Step 3: Dodaj pola do typu `Container`**

W `frontend/src/types.ts`, obok `is_transit`:

```ts
  planning_status: 'PROPOZYCJA' | 'WYSLANE' | 'POTWIERDZONE'
  notify_date_manual: boolean
  planning_sent_at: string | null
  planning_confirmed_at: string | null
```

- [ ] **Step 4: Dodaj `splitByPlanning`**

W `frontend/src/pages/queueRows.ts`:

```ts
export type PlanningStatus = 'POTWIERDZONE' | 'WYSLANE' | 'PROPOZYCJA'
export interface PlanningGroup { status: PlanningStatus; items: Container[] }

// kolejność sekcji w dniu: najpierw pewne, na końcu zgadywanki
const PLANNING_ORDER: PlanningStatus[] = ['POTWIERDZONE', 'WYSLANE', 'PROPOZYCJA']

export function splitByPlanning(items: Container[]): PlanningGroup[] {
  return PLANNING_ORDER
    .map(status => ({ status, items: items.filter(c => c.planning_status === status) }))
    .filter(group => group.items.length > 0)   // puste sekcje nie zaśmiecają dnia
}
```

- [ ] **Step 5: Uruchom test**

Run: `cd frontend && npx vitest run src/queue.planning.dom.test.tsx`
Expected: PASS (2 testy).

- [ ] **Step 6: Dodaj teksty do i18n**

W `frontend/src/i18n.ts`, w każdej z trzech sekcji językowych (pl / en / pt):

```ts
  planConfirmed: 'Potwierdzone', planSent: 'Wysłane do spedycji', planProposal: 'Propozycje',
  planSentAt: 'Wysłany do spedycji {date}, czeka na potwierdzenie',
  planEtaShift: 'ETA przesunięta o {days} dni',
  planEditConfirmed: 'Spedycja potwierdziła tę datę. Na pewno chcesz ją zmienić?',
```

(w `en`: `'Confirmed'`, `'Sent to forwarder'`, `'Proposals'`, `'Sent to forwarder {date}, awaiting confirmation'`, `'ETA shifted by {days} days'`, `'The forwarder confirmed this date. Change it anyway?'`;
w `pt`: `'Confirmadas'`, `'Enviadas ao transitário'`, `'Propostas'`, `'Enviada ao transitário {date}, a aguardar confirmação'`, `'ETA alterada em {days} dias'`, `'O transitário confirmou esta data. Alterar mesmo assim?'`)

- [ ] **Step 7: Renderuj sekcje w kolejce**

W `frontend/src/pages/QueuePage.tsx`, w renderze dnia (~linia 1073) zastąp bezpośrednie `items.map(...)` pętlą po sekcjach. Stan zwinięcia trzymaj wzorem istniejącego `hiddenCols`:

```tsx
const [collapsed, setCollapsed] = useState<string[]>(
  () => JSON.parse(localStorage.getItem('queueCollapsedPlanning') ?? '[]'))
const toggleSection = (status: string) => setCollapsed(prev => {
  const next = prev.includes(status) ? prev.filter(s => s !== status) : [...prev, status]
  localStorage.setItem('queueCollapsedPlanning', JSON.stringify(next))
  return next
})
```

W środku `<section className="day-group">`:

```tsx
{splitByPlanning(items).map(({ status, items: group }) => (
  <div key={status} className={`plan-section plan-${status.toLowerCase()}`}>
    <button type="button" className="plan-header" onClick={() => toggleSection(status)}>
      {collapsed.includes(status) ? '▸' : '▾'}{' '}
      {t(status === 'POTWIERDZONE' ? 'planConfirmed'
         : status === 'WYSLANE' ? 'planSent' : 'planProposal')} ({group.length})
    </button>
    {!collapsed.includes(status) && group.map(c => (
      /* istniejący kafelek kontenera bez zmian */
    ))}
  </div>
))}
```

Import: `import { buildDayRows, splitByPlanning, ... } from './queueRows'`.

**Filtr „zaplanowane / niezaplanowane" to te same przyciski:** „zaplanowane" zwija `WYSLANE` i `PROPOZYCJA`, „niezaplanowane" zwija `POTWIERDZONE`. Nie dodawaj osobnego mechanizmu filtrowania.

- [ ] **Step 8: Pokaż adnotacje na kafelku kontenera**

Wewnątrz kafelka, pod numerem kontenera:

```tsx
{c.planning_status === 'WYSLANE' && c.planning_sent_at && (
  <div className="plan-note">
    {t('planSentAt').replace('{date}', c.planning_sent_at.slice(0, 10))}
  </div>
)}
{etaShiftDays(c) !== null && etaShiftDays(c) !== 0 && (
  <div className="plan-note plan-alert">
    {t('planEtaShift').replace('{days}', String(etaShiftDays(c)))}
  </div>
)}
```

Helper w `queueRows.ts` (backend nie wystawia gotowej różnicy, żeby nie duplikować reguły w dwóch miejscach — `planning_eta_at_send` dołóż do `ContainerOut` w `schemas.py` i do typu `Container`):

```ts
export function etaShiftDays(c: Container): number | null {
  if (!c.planning_eta_at_send || !c.eta) return null
  const day = 24 * 60 * 60 * 1000
  return Math.round((Date.parse(c.eta) - Date.parse(c.planning_eta_at_send)) / day)
}
```

Dopisz `planning_eta_at_send: string | null` do `ContainerOut` (backend) i do typu `Container` (frontend).

- [ ] **Step 9: Dodaj bloker edycji daty**

W miejscu, gdzie kolejka zmienia `notify_date` (edycja daty i przeciąganie kafelka `moveUnlocked`), przed wysłaniem PATCH:

```tsx
if (container.planning_status === 'POTWIERDZONE' && !window.confirm(t('planEditConfirmed'))) {
  return
}
```

- [ ] **Step 10: Uruchom pełne testy frontendu i typecheck**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: brak błędów typów; wszystkie testy PASS.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/types.ts frontend/src/pages/queueRows.ts \
        frontend/src/pages/QueuePage.tsx frontend/src/i18n.ts \
        frontend/src/queue.planning.dom.test.tsx
git commit -m "feat(plan): sekcje planowania w kolejce + bloker edycji potwierdzonej daty"
```

---

### Task 9: Portal spedycji i formularz tokenowy — potwierdzanie daty

**Files:**
- Modify: `frontend/src/pages/ForwardingPage.tsx`
- Modify: `frontend/src/pages/AvizoFormPage.tsx`
- Modify: `frontend/src/i18n.ts`

**Interfaces:**
- Consumes: `GET /api/containers/plan/pending`, `POST /api/containers/{id}/plan/confirm` (Task 6); pole `delivery_date` w formularzu awizacji (Task 7).
- Produces: nic dla kolejnych zadań.

- [ ] **Step 1: Dodaj teksty do i18n**

W każdej sekcji językowej `frontend/src/i18n.ts`:

```ts
  planPending: 'Do potwierdzenia', planConfirmDate: 'Potwierdź datę',
  planYourDate: 'Proponowana data', planCounterDate: 'Twoja data',
```

(`en`: `'To confirm'`, `'Confirm date'`, `'Proposed date'`, `'Your date'`;
`pt`: `'A confirmar'`, `'Confirmar data'`, `'Data proposta'`, `'A sua data'`)

- [ ] **Step 2: Dodaj zakładkę „Do potwierdzenia" w module spedycji**

W `frontend/src/pages/ForwardingPage.tsx`, obok istniejących zakładek statusów zleceń, dodaj zakładkę pobierającą `api.get<Container[]>('/api/containers/plan/pending')`. Każdy wiersz: numer kontenera, statek, magazyn, proponowana data w `<input type="date">` (wstępnie `notify_date`) i przycisk potwierdzenia:

```tsx
const confirm = async (id: number, day: string) => {
  await api.post(`/api/containers/${id}/plan/confirm`, { delivery_date: day })
  await load()
}
```

Używaj natywnego `<input type="date">` — reszta aplikacji nie ma biblioteki datepickera i nie dodajemy jej tutaj.

- [ ] **Step 3: Dodaj pole daty do formularza tokenowego**

W `frontend/src/pages/AvizoFormPage.tsx` rozszerz interfejs `AvizoItem` o `delivery_date: string | null` oraz `planning_status: string`, dodaj kolumnę z `<input type="date">` (wartość początkowa: `notify_date`) i dołóż `delivery_date` do body POST-a:

```tsx
items: items.map(i => ({
  container_id: i.container_id, confirmed: i.confirmed,
  delivery_date: i.delivery_date,
  driver_name: i.driver_name, driver_id_no: i.driver_id_no,
  truck_no: i.truck_no, trailer_no: i.trailer_no, driver_phone: i.driver_phone,
}))
```

- [ ] **Step 4: Uruchom typecheck i testy**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: brak błędów; testy PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ForwardingPage.tsx frontend/src/pages/AvizoFormPage.tsx \
        frontend/src/i18n.ts
git commit -m "feat(plan): potwierdzanie daty w module spedycji i formularzu awizacji"
```

---

### Task 10: Serwerowa wysyłka zaproszeń

**Files:**
- Modify: `backend/app/routers/admin.py:123-162`
- Modify: `frontend/src/pages/admin/UsersTab.tsx`
- Test: `backend/tests/test_admin_invite.py`

**Interfaces:**
- Consumes: `send_html_email(recipients, subject, html, reply_to="", channel="main")` z `app/notifications.py`.
- Produces: nic dla kolejnych zadań.

- [ ] **Step 1: Napisz failing test**

Utwórz `backend/tests/test_admin_invite.py`:

```python
"""Zaproszenie użytkownika wychodzi serwerowo, a nie przez mailto w Outlooku."""
from tests.conftest import login


def test_invite_sends_email(client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.routers.admin.send_html_email",
                        lambda recipients, subject, html, **kw: sent.append((recipients, subject)))
    headers = login(client)
    response = client.post("/api/users", headers=headers, json={
        "login": "spedycja.test", "email": "spedycja@example.com",
        "role": "forwarder", "send_invite": True})
    assert response.status_code in (200, 201), response.text
    assert sent, "zaproszenie nie zostało wysłane"
    assert sent[0][0] == ["spedycja@example.com"]


def test_user_without_invite_sends_nothing(client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.routers.admin.send_html_email",
                        lambda recipients, subject, html, **kw: sent.append(recipients))
    headers = login(client)
    response = client.post("/api/users", headers=headers, json={
        "login": "bez.zaproszenia", "password": "haslo12345", "role": "logistics"})
    assert response.status_code in (200, 201), response.text
    assert sent == []
```

- [ ] **Step 2: Uruchom testy — mają nie przejść**

Run: `cd backend && python -m pytest tests/test_admin_invite.py -q`
Expected: FAIL — `sent` jest puste (mail nigdy nie wychodzi).

- [ ] **Step 3: Wyślij zaproszenie serwerowo**

W `backend/app/routers/admin.py`, w `create_user`, po `db.commit()` a przed `return serialize_user(...)`:

```python
    if send_invite and body.email:
        html = (f"<p>Utworzono konto w systemie TIMPORYE.</p>"
                f"<p>Login: <b>{new_user.login}</b><br>"
                f"Hasło tymczasowe: <b>{settings.invite_temp_password}</b></p>"
                f"<p>Przy pierwszym logowaniu system poprosi o zmianę hasła.</p>"
                f"<p><a href=\"{(settings.public_base_url or '').rstrip('/')}/login\">"
                f"Zaloguj się</a></p>")
        try:
            send_html_email([body.email], "Dostęp do systemu TIMPORYE", html,
                            channel="invite")
        except Exception as exc:  # noqa: BLE001 — konto już istnieje, mail można ponowić
            record(db, entity_type="users", entity_id=new_user.id, field="invite_error",
                   old_value=None, new_value=str(exc), user=user, note="wysyłka zaproszenia")
            db.commit()
```

Import: `from ..notifications import send_html_email`.

Wyjątek jest łapany świadomie: konto zostało już utworzone i zacommitowane, więc błąd SMTP nie może wywrócić żądania — trafia do audytu, a admin ponawia wysyłkę.

- [ ] **Step 4: Usuń otwieranie Outlooka z UI**

W `frontend/src/pages/admin/UsersTab.tsx` usuń wywołanie `openInviteMail()` po utworzeniu konta z zaproszeniem i zastąp je komunikatem, że zaproszenie zostało wysłane na podany adres.

- [ ] **Step 5: Uruchom testy**

Run: `cd backend && python -m pytest tests/test_admin_invite.py -q`
Expected: PASS (2 testy).

Run: `cd frontend && npx tsc --noEmit`
Expected: brak błędów.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin.py backend/tests/test_admin_invite.py \
        frontend/src/pages/admin/UsersTab.tsx
git commit -m "feat(admin): serwerowa wysyłka zaproszeń zamiast mailto"
```

---

### Task 11: Weryfikacja końcowa

**Files:** brak zmian — wyłącznie uruchomienie.

- [ ] **Step 1: Pełny suite backendu**

Run: `cd backend && python -m pytest -q`
Expected: wszystkie testy PASS. Suite trwa ~18 minut — uruchom w tle i poczekaj na wynik.

- [ ] **Step 2: Pełny frontend**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: brak błędów typów, wszystkie testy PASS.

- [ ] **Step 3: Spójność migracji**

Run: `cd backend && python -m alembic heads`
Expected: dokładnie jedna linia `(head)`.

- [ ] **Step 4: Migracja przechodzi na czystej bazie**

Run: `cd backend && python -m alembic upgrade head`
Expected: brak błędów.

- [ ] **Step 5: Commit, jeśli cokolwiek wymagało poprawki**

```bash
git add -A
git commit -m "test(plan): weryfikacja końcowa cyklu planowania dostawy"
```

---

## Ryzyko do obserwacji po wdrożeniu

„Wysyłamy plan tydzień przed wpłynięciem" zderza się z ruchomą ETA: tydzień przed wpłynięciem propozycja `eta + 4` bywa jeszcze niepewna, a wysyłka ją zamraża. Alert „ETA przesunięta" może odpalać częściej, niż jest to użyteczne. Jeśli tak się stanie, najtańszą reakcją jest próg (alert dopiero od 2 dni różnicy) w `eta_shift_days()` — jedno miejsce w kodzie.

## Poza zakresem tego planu

Grupowe przypisywanie jednej daty wielu kontenerom, estymacja czasu rozładunku (ML), godziny slotów 7:15 / DLT 7:00, SMS-y i kod awizacyjny kierowcy, statusy rampowe (Podstawiony / Rozładowany / Przyjęty / Rozliczony), faktury transportowe, ranking pilności. Każde z nich dostaje własny spec i plan.
