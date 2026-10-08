# Powiadomienia o zdarzeniach trackingu — plan implementacji (PR 1)

> **Dla agentów:** WYMAGANY SUB-SKILL: użyj `superpowers:subagent-driven-development`
> (zalecane) albo `superpowers:executing-plans`, żeby wykonać ten plan zadanie po zadaniu.
> Kroki mają składnię checkboxów (`- [ ]`).

**Cel:** Zdarzenia z trackingu (wypłynięcie, przybycie, wyjazd z portu), istotne zmiany
ETA i błędy trackingu same docierają do ludzi — bez zaglądania w kolejkę.

**Architektura:** Rozszerzamy `apply_result()` w `backend/app/tracking/service.py`, które
już nanosi wynik trackingu i już woła `notify()` przy zmianie ETA i statusu. Dokładamy
trzy rzeczy: próg dla zmiany ETA, powiadomienia o nowych zdarzeniach rejsu i alert
o błędzie trackingu. Nowy moduł `tracking/notify.py` trzyma decyzję „które zdarzenie
zasługuje na powiadomienie i jak brzmi jego tytuł" — `service.py` tylko go woła.

**Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), pytest.

## Global Constraints

- Język komunikatów: **polski** (jak reszta powiadomień w `notifications.py`).
- Limit długości pliku: 500 linii (konwencja repo).
- Testy uruchamiane z katalogu `backend`: `python -m pytest tests -q`.
- Ruff — `assert` dozwolony tylko w `tests/*`.
- Nie zmieniamy sygnatury `apply_result(db, container, result, source) -> dict`;
  klucze zwracanego słownika mogą przybyć, istniejące zostają
  (`eta_changed`, `status_changed`, `new_events` — sprawdzane wprost w `test_tracking.py:46`).

---

## Czego NIE budujemy (i dlaczego)

Spec zakładał trzy elementy, które w repo już są. Ich budowa byłaby duplikacją:

| Element ze speca | Co już istnieje | Decyzja |
|---|---|---|
| Kanał e-mail (`send_html_email`) | `notify()` (`notifications.py:202`) wysyła **jednocześnie** in-app, e-mail i Teams | wołamy `notify()` — kanał e-mail dostajemy gratis |
| Tabela `notification_log` do deduplikacji | `TrackingEvent` ma `UniqueConstraint(container_id, event_code, occurred_at, location)`, a `apply_result` wstawia **tylko nowe** zdarzenia (`service.py:86-99`) | powiadamiamy o zdarzeniach wstawionych w tym przebiegu — świeżo wstawiony wiersz **jest** dowodem, że jeszcze nie powiadamialiśmy. Zero nowych tabel. |
| Config `tracking_notify_emails` (stała lista) | `container_watchers()` (`notifications.py:274`) = logistyka spółki + admini + spedytor + agencja celna | pokrywa i „opiekunów", i „listę zbiorczą" |

Zostaje **jedno** nowe ustawienie: `tracking_eta_alert_days`.

**Znany kompromis:** deduplikacja opiera się na wstawieniu wiersza `TrackingEvent`.
Jeśli wysyłka maila padnie po commicie, powiadomienie przepada bezpowrotnie (nie ma
kolejki ponowień). Świadome — alternatywą jest tabela stanu wysyłki, której nie
potrzebujemy przy jednym kanale. Wrócić, jeśli maile zaczną ginąć.

---

## Struktura plików

| Plik | Odpowiedzialność |
|---|---|
| `backend/app/tracking/notify.py` *(nowy)* | jedyne miejsce z wiedzą „które zdarzenie powiadamia i jakim tytułem" |
| `backend/app/tracking/service.py` *(modyfikacja)* | wywołuje powiadomienia; nie zna reguł |
| `backend/app/config.py` *(modyfikacja)* | `tracking_eta_alert_days` |
| `backend/tests/test_tracking_notify.py` *(nowy)* | testy wszystkich trzech zachowań |

---

### Task 1: Próg dla zmiany ETA

Dziś **każda** zmiana ETA generuje powiadomienie (`service.py:48-51`). ETA armatorów
drga codziennie o godziny, więc to szum. Powiadamiamy dopiero od progu w dniach.

**Files:**
- Modify: `backend/app/config.py` (obok `tracking_interval_hours`, linia 50)
- Modify: `backend/app/tracking/service.py:41-51`
- Test: `backend/tests/test_tracking_notify.py` *(nowy)*

**Interfaces:**
- Produces: `settings.tracking_eta_alert_days: int` (domyślnie 2) — używane też w Task 2.

- [x] **Krok 1: Napisz failujący test**

Utwórz `backend/tests/test_tracking_notify.py`:

```python
import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Container, Notification
from app.tracking.base import TrackedEvent, TrackingResult
from app.tracking.mock import MockProvider
from app.tracking.service import sync_container

VALID_NO = "MSDU0806613"


def _create_container(client, headers, **extra):
    companies = client.get("/api/companies", headers=headers).json()
    borealis = next(c["id"] for c in companies if c["code"] == "BOREALIS")
    body = {"container_no": VALID_NO, "company_id": borealis,
            "status": "W_TRANSPORCIE", **extra}
    response = client.post("/api/containers", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _result(eta=None, arrived=False, events=(), vessel="MSC X"):
    return TrackingResult(container_no=VALID_NO, eta=eta, vessel=vessel,
                          pod="GDANSK", arrived=arrived, events=list(events))


def _notifications(db, container_id, kind):
    return list(db.scalars(select(Notification).where(
        Notification.container_id == container_id, Notification.kind == kind)))


def test_eta_drift_below_threshold_is_silent(client, admin_headers):
    """Przesunięcie ETA o 1 dzień przy progu 2 nie powiadamia, ale ETA się zapisuje."""
    created = _create_container(client, admin_headers, eta="2026-07-10")
    provider = MockProvider()
    provider.set_result(_result(eta=datetime.date(2026, 7, 11)))

    with SessionLocal() as db:
        container = db.get(Container, created["id"])
        summary = sync_container(db, container, provider)
        assert summary["eta_changed"] is True
        assert container.eta == datetime.date(2026, 7, 11)
        assert _notifications(db, created["id"], "eta") == []


def test_eta_shift_at_threshold_notifies(client, admin_headers):
    """Przesunięcie o 3 dni przekracza próg 2 — leci powiadomienie z dopiskiem."""
    created = _create_container(client, admin_headers, eta="2026-07-10")
    provider = MockProvider()
    provider.set_result(_result(eta=datetime.date(2026, 7, 13)))

    with SessionLocal() as db:
        container = db.get(Container, created["id"])
        sync_container(db, container, provider)
        alerts = _notifications(db, created["id"], "eta")
        assert len(alerts) == 1
        assert "OPÓŹNIENIE" in alerts[0].title


def test_first_eta_from_tracking_notifies(client, admin_headers):
    """Kontener bez ETA dostaje ją po raz pierwszy — zawsze warte powiadomienia."""
    created = _create_container(client, admin_headers)
    provider = MockProvider()
    provider.set_result(_result(eta=datetime.date(2026, 7, 13)))

    with SessionLocal() as db:
        container = db.get(Container, created["id"])
        sync_container(db, container, provider)
        assert len(_notifications(db, created["id"], "eta")) == 1
```

- [x] **Krok 2: Uruchom test — musi failować**

```bash
cd backend && python -m pytest tests/test_tracking_notify.py -v
```

Oczekiwane: `test_eta_drift_below_threshold_is_silent` FAIL — powstaje 1 powiadomienie
zamiast 0 (dziś powiadamia każda zmiana). Dwa pozostałe testy przechodzą już teraz.

- [x] **Krok 3: Dodaj ustawienie w `config.py`**

Wstaw bezpośrednio pod `tracking_interval_hours` (linia 50):

```python
    # próg powiadomienia o zmianie ETA — drobne drgania ETA armatora to szum
    tracking_eta_alert_days: int = Field(default=2, ge=0)
```

- [x] **Krok 4: Zastosuj próg w `apply_result`**

W `backend/app/tracking/service.py` zamień blok ETA (linie 41-51) na:

```python
    if result.eta and result.eta != container.eta:
        record(db, entity_type="containers", entity_id=container.id, field="eta",
               old_value=container.eta, new_value=result.eta, user=None, note=note)
        old_eta = container.eta
        container.eta = result.eta
        summary["eta_changed"] = True
        # ETA armatora drga o godziny — powiadamiamy dopiero od progu w dniach.
        # Pierwsze ETA (brak starego) jest zawsze warte powiadomienia.
        shift = abs((result.eta - old_eta).days) if old_eta else None
        if shift is None or shift >= settings.tracking_eta_alert_days:
            suffix = " (OPÓŹNIENIE)" if old_eta and result.eta > old_eta else ""
            notify(db, company_watchers(db, container.company_id), kind="eta",
                   title=f"Zmiana ETA {container.container_no}: "
                         f"{old_eta or '—'} → {result.eta}{suffix}",
                   container_id=container.id)
```

- [x] **Krok 5: Uruchom testy — muszą przejść**

```bash
cd backend && python -m pytest tests/test_tracking_notify.py tests/test_tracking.py -v
```

Oczekiwane: PASS. `test_tracking.py` musi przejść bez zmian — sprawdza `summary`,
nie powiadomienia.

- [x] **Krok 6: Commit**

```bash
git add backend/app/config.py backend/app/tracking/service.py backend/tests/test_tracking_notify.py
git commit -m "feat(tracking): próg powiadomienia o zmianie ETA (TRACKING_ETA_ALERT_DAYS)"
```

---

### Task 2: Powiadomienia o zdarzeniach rejsu

Kontener wypływa, przypływa i wyjeżdża z portu — dziś nikt się o tym nie dowiaduje,
zdarzenie tylko ląduje w bazie.

**Files:**
- Create: `backend/app/tracking/notify.py`
- Modify: `backend/app/tracking/service.py:86-103`
- Test: `backend/tests/test_tracking_notify.py` (dopisanie)

**Interfaces:**
- Consumes: `settings.tracking_eta_alert_days` z Task 1 (niewykorzystywane tutaj,
  ale ten sam moduł konfiguracji).
- Produces:
  - `NOTIFIABLE: dict[str, str]` — kod zdarzenia → opis po polsku
  - `event_title(container_no: str, event: TrackingEvent) -> str`
  - `notify_events(db: Session, container: Container, events: list[TrackingEvent]) -> int`
    — zwraca liczbę wysłanych powiadomień; sam filtruje, co jest godne wysyłki.

- [x] **Krok 1: Napisz failujący test**

Dopisz na końcu `backend/tests/test_tracking_notify.py`:

```python
def test_voyage_events_notify_once(client, admin_headers):
    """DEPART powiadamia raz; powtórny sync tego samego zdarzenia już nie."""
    created = _create_container(client, admin_headers)
    provider = MockProvider()
    when = datetime.datetime(2026, 7, 1, 8, 0)
    provider.set_result(_result(
        events=[TrackedEvent("DEPART", "Wyjście z portu", "SHANGHAI", "MSC X", when)]))

    with SessionLocal() as db:
        container = db.get(Container, created["id"])
        sync_container(db, container, provider)
        alerts = _notifications(db, created["id"], "tracking")
        assert len(alerts) == 1
        assert "SHANGHAI" in alerts[0].title

        sync_container(db, container, provider)      # ten sam wynik jeszcze raz
        assert len(_notifications(db, created["id"], "tracking")) == 1


def test_estimated_event_does_not_notify(client, admin_headers):
    """Zdarzenie prognozowane trafia do bazy, ale nie powiadamia."""
    created = _create_container(client, admin_headers)
    provider = MockProvider()
    when = datetime.datetime(2026, 7, 20, 8, 0)
    provider.set_result(_result(events=[
        TrackedEvent("DISCHARGE", "Wyładunek", "GDANSK", "MSC X", when,
                     is_estimated=True)]))

    with SessionLocal() as db:
        container = db.get(Container, created["id"])
        summary = sync_container(db, container, provider)
        assert summary["new_events"] == 1
        assert _notifications(db, created["id"], "tracking") == []


def test_uninteresting_event_does_not_notify(client, admin_headers):
    """Nie każde zdarzenie zasługuje na maila — LOAD jest tylko w osi czasu."""
    created = _create_container(client, admin_headers)
    provider = MockProvider()
    when = datetime.datetime(2026, 7, 1, 6, 0)
    provider.set_result(_result(events=[
        TrackedEvent("LOAD", "Załadunek", "SHANGHAI", "MSC X", when)]))

    with SessionLocal() as db:
        container = db.get(Container, created["id"])
        summary = sync_container(db, container, provider)
        assert summary["new_events"] == 1
        assert _notifications(db, created["id"], "tracking") == []
```

- [x] **Krok 2: Uruchom test — musi failować**

```bash
cd backend && python -m pytest tests/test_tracking_notify.py::test_voyage_events_notify_once -v
```

Oczekiwane: FAIL — `assert len(alerts) == 1` dostaje 0 (nic jeszcze nie powiadamia).

- [x] **Krok 3: Utwórz `backend/app/tracking/notify.py`**

```python
"""Reguły powiadamiania o zdarzeniach trackingu.

Jedyne miejsce z wiedzą, KTÓRE zdarzenie zasługuje na powiadomienie i jak brzmi
jego tytuł — `service.py` tylko woła `notify_events`.

Deduplikacja jest darmowa: `apply_result` wstawia wyłącznie zdarzenia nieobecne
jeszcze w bazie (chroni je `UniqueConstraint` na `tracking_events`), więc świeżo
wstawiony wiersz z definicji nie był jeszcze przedmiotem powiadomienia.
"""
from sqlalchemy.orm import Session

from ..models import Container, TrackingEvent
from ..notifications import container_watchers, notify

# kody zdarzeń warte powiadomienia -> fragment tytułu po polsku.
# Reszta (LOAD, TRANSSHIP, …) żyje tylko na osi czasu kontenera.
NOTIFIABLE = {
    "DEPART": "wypłynął",
    "ARRIVE": "przypłynął do portu",
    "DISCHARGE": "rozładowany",
    "GATE_OUT": "opuścił port",
}


def event_title(container_no: str, event: TrackingEvent) -> str:
    """Tytuł powiadomienia, np. „Kontener MSDU0806613 wypłynął — SHANGHAI (2026-07-01)"."""
    parts = [f"Kontener {container_no} {NOTIFIABLE[event.event_code]}"]
    detail = " ".join(p for p in (event.location,) if p)
    if detail:
        parts.append(f" — {detail}")
    if event.occurred_at:
        parts.append(f" ({event.occurred_at.date()})")
    return "".join(parts)


def notify_events(db: Session, container: Container,
                  events: list[TrackingEvent]) -> int:
    """Powiadamia o nowych zdarzeniach rejsu. Zwraca liczbę wysłanych powiadomień.

    Pomija zdarzenia prognozowane — powiadamiamy wyłącznie o faktach.
    """
    sent = 0
    watchers = None
    for event in events:
        if event.is_estimated or event.event_code not in NOTIFIABLE:
            continue
        if watchers is None:                       # leniwie: zwykle nie ma o czym mówić
            watchers = container_watchers(db, container)
        sent += notify(db, watchers, kind="tracking",
                       title=event_title(container.container_no, event),
                       container_id=container.id)
    return sent
```

- [x] **Krok 4: Zepnij z `service.py`**

W `backend/app/tracking/service.py` dodaj import obok pozostałych względnych
(pod linią 16, `from .safecube import SafeCubeProvider`):

```python
from .notify import notify_events
```

Następnie w `apply_result` zamień pętlę wstawiającą zdarzenia (linie 89-99) na wersję
zbierającą nowe wiersze, i powiadom po pętli:

```python
    fresh: list[TrackingEvent] = []
    for event in result.events:
        key = (event.event_code, event.occurred_at, event.location)
        if key in existing:
            continue
        existing.add(key)
        row = TrackingEvent(
            container_id=container.id, event_code=event.event_code,
            description=event.description, location=event.location,
            vessel=event.vessel, occurred_at=event.occurred_at,
            is_estimated=event.is_estimated, source=source)
        db.add(row)
        fresh.append(row)
        summary["new_events"] += 1
    notify_events(db, container, fresh)
```

- [x] **Krok 5: Uruchom testy — muszą przejść**

```bash
cd backend && python -m pytest tests/test_tracking_notify.py tests/test_tracking.py -v
```

Oczekiwane: PASS, wszystkie.

- [x] **Krok 6: Commit**

```bash
git add backend/app/tracking/notify.py backend/app/tracking/service.py backend/tests/test_tracking_notify.py
git commit -m "feat(tracking): powiadomienia o zdarzeniach rejsu (DEPART/ARRIVE/DISCHARGE/GATE_OUT)"
```

---

### Task 3: Alert o błędzie trackingu — raz na kontener

`sync_container` zapisuje `tracking_error` (`service.py:117`), ale nikt tego nie widzi.
Kontener z literówką w numerze może miesiącami cicho nie mieć danych.

Alert idzie **raz** — dopóki błąd trwa, nie powtarzamy. Odpytywanie toczy się dalej.

**Files:**
- Modify: `backend/app/tracking/notify.py`
- Modify: `backend/app/tracking/service.py:113-119`
- Test: `backend/tests/test_tracking_notify.py` (dopisanie)

**Interfaces:**
- Produces: `notify_error(db: Session, container: Container, message: str) -> int`

- [x] **Krok 1: Napisz failujący test**

Najpierw uzupełnij importy **na górze** `backend/tests/test_tracking_notify.py` —
dopisz `import pytest` pod `import datetime` oraz rozszerz import z `app.tracking.base`:

```python
from app.tracking.base import TrackedEvent, TrackingError, TrackingResult
```

Następnie dopisz testy na końcu pliku:

```python
def test_tracking_error_alerts_once(client, admin_headers):
    """Błąd trackingu alertuje przy pierwszym wystąpieniu; kolejne są ciche."""
    created = _create_container(client, admin_headers)
    provider = MockProvider()
    provider.set_error(TrackingError("Kontener nieznany w SafeCube."))

    with SessionLocal() as db:
        container = db.get(Container, created["id"])
        for _ in range(2):
            with pytest.raises(TrackingError):
                sync_container(db, container, provider)
        alerts = _notifications(db, created["id"], "tracking_error")
        assert len(alerts) == 1
        assert "nieznany" in alerts[0].title


def test_recovered_container_alerts_again(client, admin_headers):
    """Po udanym syncu błąd jest wyczyszczony — kolejna awaria alertuje na nowo."""
    created = _create_container(client, admin_headers)
    provider = MockProvider()
    provider.set_error(TrackingError("SafeCube niedostępny."))

    with SessionLocal() as db:
        container = db.get(Container, created["id"])
        with pytest.raises(TrackingError):
            sync_container(db, container, provider)

        provider.set_result(_result(eta=datetime.date(2026, 7, 13)))
        sync_container(db, container, provider)      # sukces czyści tracking_error
        assert container.tracking_error == ""

        provider.set_error(TrackingError("SafeCube niedostępny."))
        with pytest.raises(TrackingError):
            sync_container(db, container, provider)
        assert len(_notifications(db, created["id"], "tracking_error")) == 2
```

- [x] **Krok 2: Dostosuj testy do realnej sygnatury `MockProvider.set_error`**

`set_error` **już istnieje** (`backend/app/tracking/mock.py:18`), ale przyjmuje
`(container_no, message)` — nie obiekt wyjątku. Nie zmieniaj mocka; dostosuj testy.

Sprawdź aktualny stan:

```bash
cd backend && grep -n "def set_error\|def set_result\|def fetch\|responses" app/tracking/mock.py
```

W obu testach z Kroku 1 zamień wywołania:

```python
    provider.set_error(VALID_NO, "Kontener nieznany w SafeCube.")
```

oraz w `test_recovered_container_alerts_again`:

```python
    provider.set_error(VALID_NO, "SafeCube niedostępny.")
```

**Uwaga:** `set_error` nie zeruje `self.responses`, więc w `test_recovered_container_alerts_again`
kolejność ma znaczenie — po `set_result(...)` trzeba ponownie wywołać `set_error(...)`,
żeby wrócić do ścieżki błędu (tak jak w treści testu). Jeśli okaże się, że `set_result`
nie usuwa wpisu błędu i sync po odzyskaniu nadal rzuca, zgłoś to zamiast obchodzić —
to znak, że mock wymaga poprawki w osobnym kroku.

Import `TrackingError` w teście nadal jest potrzebny do `pytest.raises`.

- [x] **Krok 3: Uruchom test — musi failować**

```bash
cd backend && python -m pytest tests/test_tracking_notify.py::test_tracking_error_alerts_once -v
```

Oczekiwane: FAIL — `assert len(alerts) == 1` dostaje 0.

- [x] **Krok 4: Dodaj `notify_error` do `notify.py`**

Dopisz na końcu `backend/app/tracking/notify.py`:

```python
def notify_error(db: Session, container: Container, message: str) -> int:
    """Alert o błędzie trackingu — tylko przy PIERWSZYM wystąpieniu.

    Warunkiem jest pusty `tracking_error` w chwili wywołania: dopóki błąd trwa,
    pole pozostaje wypełnione i alert się nie powtarza. Udany sync czyści pole,
    więc nawrót awarii zaalarmuje ponownie.
    """
    if container.tracking_error:
        return 0
    return notify(db, container_watchers(db, container), kind="tracking_error",
                  title=f"Tracking {container.container_no}: {message[:150]}",
                  container_id=container.id)
```

- [x] **Krok 5: Zepnij z `service.py`**

Rozszerz import w `backend/app/tracking/service.py`:

```python
from .notify import notify_error, notify_events
```

W `sync_container` zamień obsługę wyjątku (linie 115-119) na:

```python
    except TrackingError as exc:
        notify_error(db, container, str(exc))     # przed nadpisaniem tracking_error
        container.tracked_at = utcnow()
        container.tracking_error = str(exc)[:300]
        db.commit()
        raise
```

Kolejność jest istotna: `notify_error` czyta `container.tracking_error`, żeby
rozpoznać, czy błąd jest nowy — musi zobaczyć stan **sprzed** zapisu.

- [x] **Krok 6: Uruchom pełny zestaw testów**

```bash
cd backend && python -m pytest tests -q
```

Oczekiwane: wszystkie PASS. Zwróć szczególną uwagę na `test_tracking.py`
i `test_safecube_retry.py` — dotykają tej samej ścieżki błędu.

- [x] **Krok 7: Commit**

```bash
git add backend/app/tracking/notify.py backend/app/tracking/service.py backend/app/tracking/mock.py backend/tests/test_tracking_notify.py
git commit -m "feat(tracking): alert o błędzie trackingu — raz na kontener, do czasu odzyskania"
```

---

## Weryfikacja end-to-end

Po wszystkich zadaniach, z `TRACKING_PROVIDER=mock`:

1. `cd backend && python -m pytest tests -q` — cały zestaw zielony.
2. `python -m pytest tests/test_tracking_notify.py -v` — 8 testów, wszystkie PASS.
3. Ręcznie: uruchom panel, wejdź na kontener, kliknij synchronizację trackingu
   i sprawdź, że w dzwonku powiadomień pojawia się wpis o zdarzeniu, a przy drugim
   przebiegu **nie** dubluje się.
4. `ruff check backend` — bez nowych zastrzeżeń.

## Poza zakresem tego PR-a

- Kolumny trackingowe w arkuszu i adaptacyjny scheduler → PR 2
- Wstrzymywanie konfliktów sync i ekran „Stan synchronizacji" → PR 3
- Ponowienia nieudanych wysyłek e-mail (patrz „Znany kompromis" wyżej)
