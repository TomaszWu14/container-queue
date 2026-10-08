# Kompletność dokumentów celnych — design

Data: 2026-09-01 · Status: zatwierdzony przez użytkownika

## Cel

Domknięcie obiegu dokumentów i odpraw: system sam wie, jakich dokumentów brakuje
kontenerowi w obiegu celnym, upomina odpowiedzialnych przed ETA i ostrzega przy
wysyłce niekompletnego pakietu do agencji. Pierwszy krok roadmapy (dalej, w kolejności:
awizacje/magazyn → integracje/automatyzacja → analityka Faza 2).

## Decyzje (z brainstormingu)

1. Kompletność = **checklista typów dokumentów** definiowana w panelu admina
   (globalna; wariant per-typ-ładunku świadomie odrzucony — YAGNI).
2. Przypomnienia: **X dni przed ETA** → dzwonek + e-mail do obserwatorów spółki
   (logistyka/zakupy); próg konfigurowalny w adminie, domyślnie 7 dni.
3. Braki **nie blokują** wysyłki do agencji — modal ostrzegawczy „wysłać mimo to?",
   decyzja człowieka, fakt w audycie.

## Zakres

### 1. Słownik typów dokumentów (admin)

- Model `DocumentType(id, name unique, sort_order, is_active, is_required)` —
  wzór `CustomsCaseStatus`/`ProblemType`.
- Endpoints w stylu case-statuses: `GET /api/customs/document-types`
  (viewer, `active_only`), `POST`/`PATCH` (admin).
- Zakładka admina „Typy dokumentów" (wzór `CaseStatusesTab`) + kolumna/przełącznik
  „wymagany".
- Migracja Alembic + wpis w dev-shimie (`ensure_new_columns`).

### 2. Typowanie załączników

- `Attachment.document_type_id` (nullable FK, index). Stare/nietypowe pliki = bez typu.
- Upload w `AttachmentsPanel` dostaje select typu (opcjonalny, domyślnie „—").
- `AttachmentOut` + lista załączników zwraca `document_type_id`/`document_type_name`.
- Kompletność **wyliczana na żywo** (bez przechowywanej flagi): kontener w obiegu
  celnym (przypisana agencja LUB `customs_status != BRAK`) jest kompletny, gdy każdy
  aktywny `is_required` typ ma ≥1 załącznik. Helper backendowy `missing_document_types()`
  zwracający listę braków — jedno źródło prawdy dla UI, wysyłki i alertów.
- Auto-przejście `document_status BRAK→ZALACZONE` przy pierwszym otypowanym załączniku
  (nie cofa WYSLANE).

### 3. Wysyłka z ostrzeżeniem

- `POST /customs/containers/{id}/send-docs` przyjmuje body `{force: bool = false}`;
  przy brakach i `force=false` → 409 z listą braków w `detail`.
- Front: modal „Brakuje: … Wysłać mimo to?" → ponowna wysyłka z `force=true`.
- Wysyłka z brakami odnotowana w audycie (note zawiera listę braków).

### 4. Przypomnienia przed ETA

- Ustawienie `docs_reminder_days` (admin Settings, domyślnie 7).
- Rozszerzenie istniejącego cyklu `check_customs_alerts`: kontener w obiegu celnym
  + `eta ≤ today + N` + braki → `notify(kind="docs-missing")` do obserwatorów spółki
  (dzwonek + istniejące kanały e-mail/Teams). Dedup: raz dziennie per kontener
  (jak `customs-delay`).

### 5. Widoczność braków

- Badge „Braki dok." (bursztyn, styl rodziny `ds-*`) na tablicy odpraw (`/api/customs/board`
  zwraca `missing_documents: string[]`) i w szczegółach kontenera (panel plików pokazuje
  listę braków).
- Filtr „bez kompletu" na tablicy odpraw. Bez zmian w siatce kolejki.

## Poza zakresem

- Wymagalność typów zależna od kraju/trybu/towaru.
- OCR/rozpoznawanie typu z pliku.
- Twarda blokada wysyłki.

## Testy (strażnicy regresji)

- Słownik: CRUD/uprawnienia (403 nie-admin, 409 duplikat), dezaktywacja wyklucza
  typ z checklisty.
- Kompletność: braki liczone tylko dla obiegu celnego; typowany załącznik zamyka brak;
  auto `BRAK→ZALACZONE` nie cofa `WYSLANE`.
- Wysyłka: 409 z listą braków bez `force`; `force=true` wysyła + audyt z listą braków.
- Alerty: przypomnienie ≤ N dni przed ETA, raz dziennie, brak alertu dla kompletnych
  i poza obiegiem celnym.
- Dev-shim guard (`test_dev_schema_shim`) przechodzi dla nowej kolumny.
