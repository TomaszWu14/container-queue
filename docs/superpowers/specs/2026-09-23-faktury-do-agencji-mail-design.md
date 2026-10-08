# Faktury do agencji celnej — mail z Excelem i PDF-ami (design)

Data: 2026-09-23 · Status: **zastąpiony 2026-09-24** — patrz sekcja „Zmiana 2026-09-24” (szkic .eml zamiast wysyłki)

## Zmiana 2026-09-24: szkic .eml zamiast wysyłki Graph
**Decyzja użytkownika:** bez uprawnień IT do skrzynek i bez Microsoft Graph. Serwer niczego nie
wysyła — generuje szkic `.eml`, który Outlook otwiera jako **nową, edytowalną wiadomość**;
użytkownik sam klika „Wyślij” ze swojego konta.

**Dlaczego:** wysyłka z serwera wymaga zgody IT (uprawnienia aplikacji do skrzynek / Graph
`Mail.Send`) i konfiguracji kanału; szkic nie wymaga niczego po stronie IT, mail wychodzi z
prawdziwej skrzynki nadawcy (trafia do jego „Wysłanych”), a użytkownik może poprawić treść/adresatów
przed wysłaniem. Koszt: aplikacja nie wie, czy mail faktycznie wyszedł.

**Co zostaje z tej spec:** adresaci (Do: `CustomsAgency.email` agencji kontenera; DW: `Company.avizo_cc`,
bez duplikatów i bez adresów z „Do”), temat `Faktury — {container_no} — {spółka}`, treść HTML+text
(wartości escapowane), załączniki (Excel `InvoiceBatch.attachment` + PDF-y zatwierdzonych faktur
`INVOICE_LIKE_KINDS`, `InvoiceJob.stored_name`, nazwy przez `safe_filename`), odmowy 409 (brak agencji /
agencja bez e-maila / Excel nieaktualny / brak pliku na dysku), audyt kontenera
„przygotowano szkic maila do agencji”. Nadawcy nie wpisujemy (brak `From`) — Outlook użyje konta użytkownika.

**Co odpada:** zmiany `mailer.py` (załączniki SMTP/Graph), `GraphMailSender`, limit rozmiaru i 413,
podgląd/modal, pola `sent_to_agency_*` + migracja (nie wiemy, czy wysłano), przełączanie etykiety `avizo_cc`.

**Implementacja:**
- `backend/app/eml.py` — `build_eml(to, cc, subject, html, text, attachments) -> bytes` (stdlib
  `EmailMessage`): `X-Unsent: 1` (Outlook = szkic), multipart/alternative text+html (quoted-printable),
  załączniki z Content-Type i nazwą (RFC 2231 dla polskich znaków).
- `GET /api/invoice-batches/{id}/agency-mail.eml` (`routers/invoice_agency.py`) — rola `docs_senders`,
  dostęp przez `_get_batch` (izolacja kontenera), `message/rfc822` + `Content-Disposition: attachment;
  filename="faktury_<container_no>.eml"`.
- Front: przycisk „Przygotuj maila do agencji” w `InvoiceBatchesPanel.tsx` (gdy jest Excel; wyłączony
  z podpowiedzią przy nieaktualnym Excelu) → `downloadFile`; błąd 409 w komunikacie panelu
  (`downloadBlob` przekazuje `detail` backendu).

---
*Poniżej pierwotny projekt (2026-09-23) — historycznie.*

## Cel
Wgrane faktury (paczka CIPL), po weryfikacji i wygenerowaniu Excela, jednym kliknięciem trafiają
**mailem** do agencji celnej — z Excelem i oryginalnymi PDF-ami faktur w załącznikach.

## Stan zastany (co już jest i zostaje bez zmian)
- Wgranie PDF → `POST /api/containers/{id}/invoice-batches` (ekstrakcja/OCR, dopasowanie do kartoteki).
- Weryfikacja pozycji → `PUT /api/invoice-jobs/{id}/review`.
- Excel → `POST /api/invoice-batches/{id}/export` (stały kontrakt 11 kolumn, `invoices/excel.py`),
  plik jako `Attachment` kontenera (`InvoiceBatch.attachment`).
- `POST /api/customs/containers/{id}/send-docs` — tylko powiadomienie in-app do kont agencji;
  **zostaje bez zmian** (steruje `document_status`).
- Luka: mailer (`mailer.py`) nie obsługuje załączników; nikt nie wysyła maila na `CustomsAgency.email`.

## Decyzje (brainstorming 2026-09-23)
| Pytanie | Decyzja |
|---|---|
| Czego brakuje | Tylko mail z załącznikami; wgrywanie/przegląd/Excel bez zmian |
| Załączniki | Excel paczki + PDF-y zatwierdzonych faktur tej paczki |
| Skąd wysyłka | Nowy przycisk przy paczce faktur („Wyślij do agencji”) |
| Adresaci | Do: agencja; DW: wysyłający + mail grupowy spółki |
| Mail grupowy | Per spółka w panelu — reużycie `Company.avizo_cc` (nowa etykieta) |
| Podejście | A: rozszerzenie istniejącego mailera, wysyłka synchroniczna, bez nowej kolumny CC |

## Backend

### `mailer.py`
- `MailAttachment(filename: str, content: bytes, content_type: str)`; `Mail.attachments: list[MailAttachment] = []`.
- `SmtpMailSender`: `EmailMessage.add_attachment(...)` per plik.
- `GraphMailSender`: `message.attachments = [{"@odata.type": "#microsoft.graph.fileAttachment",
  "name", "contentType", "contentBytes": base64}]`.
- `ConsoleMailSender`: bez zmian (outbox trzyma `Mail` z załącznikami — do asercji w testach).
- Awizacja nie zmienia zachowania (pusta lista).

### `invoices/agency_mail.py` (nowy, bez HTTP poza `HTTPException`)
- `build_agency_mail(db, batch, user) -> Mail`:
  - **Do:** `split_addresses(agency.email)` agencji przypisanej do kontenera (`container.customs_agency_id`).
  - **DW:** `user.email` + `split_addresses(container.company.avizo_cc)`; bez duplikatów i bez adresów z „Do”.
  - **Reply-To:** `user.email` (gdy pusty — brak).
  - **Temat:** `Faktury — {container_no} — {company.name}`.
  - **Treść (HTML + text):** nr kontenera, B/L (jeśli jest), liczba faktur, lista plików; wartości escapowane.
  - **Załączniki:** Excel `batch.attachment` + pliki `InvoiceJob.stored_name` dla jobów fakturowych
    (`doc_kind in INVOICE_LIKE_KINDS`) w statusie `confirmed`; nazwy przez `safe_filename`.
- `agency_mail_preview(db, batch, user) -> dict` — te same dane bez treści plików:
  `{to, cc, subject, files: [{filename, size}], total_size, limit_mb, already_sent_at, already_sent_by}`.
- Odmowy (wspólne dla preview i wysyłki):
  | Warunek | Kod | Komunikat |
  |---|---|---|
  | kontener bez agencji | 409 | „Kontener nie ma przypisanej agencji celnej.” |
  | agencja bez e-maila | 409 | „Agencja {nazwa} nie ma adresu e-mail.” |
  | brak Excela lub `excel_current == False` | 409 | „Najpierw wygeneruj Excel ponownie.” |
  | brak pliku na dysku | 409 | „Brak pliku: {nazwa}.” (nic nie wychodzi) |
  | suma załączników > limit | 413 | „Załączniki mają X MB, limit Y MB (kanał {backend}).” |
- Limit: `settings.mail_max_attachments_mb`; puste/0 → domyślnie 3 dla `graph`, 25 dla pozostałych.

### Endpointy (nowy `routers/invoice_agency.py`)
- Osobny router, bo `routers/invoices.py` ma 448 linii (limit 500, strażnik w CI); rejestracja w `main.py`
  obok routera faktur. Reużywa `_get_batch` z `routers/invoices.py` i `docs_senders` z `routers/customs.py`.
- `GET /api/invoice-batches/{id}/agency-mail-preview` → podgląd (bez wysyłki).
- `POST /api/invoice-batches/{id}/send-to-agency`:
  - rola: jak `send-docs` (`docs_senders`); dostęp przez `_get_batch` (izolacja kontenera);
  - adresy **wyłącznie z bazy** — endpoint nie przyjmuje adresów w body;
  - wysyłka synchroniczna: `mailer.get_sender()` + `mailer.send_with_retry()`;
  - błąd → audyt „nieudana wysyłka faktur do agencji” + **502** z treścią błędu;
  - sukces → `batch.sent_to_agency_at = utcnow()`, `batch.sent_to_agency_by_id = user.id`,
    audyt kontenera „Faktury wysłane do agencji {nazwa} (Do: …, DW: …, N plików)”,
    odpowiedź `{sent_at, to, cc, files}`;
  - **nie** zmienia `container.document_status`.

### Model i migracja
- `InvoiceBatch.sent_to_agency_at: DateTime | None`, `InvoiceBatch.sent_to_agency_by_id: FK users | None`.
- Jedna migracja od jedynej głowy alembica; wpis w `ensure_new_columns`, dopóki ten mechanizm istnieje.
- `InvoiceBatchOut` + `sent_to_agency_at`, `sent_to_agency_by` (imię i nazwisko / login).
- Config: `mail_max_attachments_mb: int = 0`.

## Frontend (`InvoiceBatchesPanel.tsx` + nowy `AgencyMailModal.tsx`)
- Przycisk **„Wyślij do agencji”** obok „Pobierz Excel”, widoczny gdy `attachment_id`.
  Wyłączony z `title`-podpowiedzią, gdy: `!excel_current` („Wygeneruj Excel ponownie”),
  brak agencji („Najpierw zleć odprawę agencji”), agencja bez e-maila („Uzupełnij e-mail agencji”).
  Stan agencji/e-maila bierzemy z odpowiedzi preview (błąd 409 = powód wyłączenia).
- Klik → modal w osobnym pliku `AgencyMailModal.tsx` (istniejący komponent `Modal` z `components.tsx`, Esc zamyka): Do / DW / temat, lista plików z rozmiarami
  i sumą; przy ponownej wysyłce ostrzeżenie „Ta paczka została już wysłana {data} przez {osoba}”.
  Przyciski „Wyślij” / „Anuluj”; „Wyślij” zablokowany na czas żądania.
- Po sukcesie w wierszu paczki szary tekst „Wysłano do {agencja} · {dd.mm.rrrr gg:mm}”
  (stonowanie — bez kolorowego tła). Błąd → istniejący `error` panelu.
- Panel Spółki (`admin/CompaniesTab.tsx`): etykieta `avizo_cc` → „Mail grupowy logistyki
  (DW awizacji i faktur do agencji)”. Pole/API bez zmian.
- Teksty w `i18n.ts` (PL + EN).

## Testy
- `test_mailer.py`: SMTP z załącznikiem (część MIME z nazwą/typem); Graph (JSON ma `fileAttachment` z base64).
- `test_agency_mail.py`: Do/DW bez duplikatów; tylko zatwierdzone faktury, bez innych rodzajów dokumentów;
  każda odmowa z tabeli; limit rozmiaru.
- Endpoint: sukces ustawia `sent_to_agency_at`, audyt i outbox konsoli; błąd kanału → 502 + audyt;
  użytkownik innej spółki → 404; body z adresami jest ignorowane.
- Vitest (`invoices.dom.test.tsx`): przycisk wyłączony w 3 stanach; modal pokazuje podgląd;
  po wysłaniu informacja „Wysłano do…”.
- DoD: pełny pytest, vitest, build, `scripts/check_file_lengths.py`, zrzut z własnej instancji (:8010/:5180).

## Poza zakresem
Sesja uploadu Graph dla dużych plików; edycja treści/adresatów przed wysyłką; szablony per agencja;
wysyłka w tle z logiem maili; zmiana obiegu `send-docs`.
