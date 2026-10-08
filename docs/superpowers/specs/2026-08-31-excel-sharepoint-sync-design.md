# Sync kolejki Excel (SharePoint) ↔ TIMPORYE — projekt

Data: 2026-08-31 (zaktualizowany po zmianie zakresu na dwukierunkowość)
Status: Faza A zatwierdzona do wdrożenia; Faza B zaprojektowana, do zaplanowania później

## Cel

Kolejka kontenerów żyje w Excelu na SharePoincie i jest edytowana przez
operatora. Docelowo: **jedne dane, dwa edytowalne widoki (Excel i aplikacja)** — zmiana w
którymkolwiek propaguje do drugiego, z powiadomieniem i historią zmian w aplikacji.

## Ograniczenie kluczowe (przesądza architekturę)

**Brak zgody IT na rejestrację aplikacji w Entra ID (Azure AD).** To wyklucza JAKIKOLWIEK
serwerowy dostęp do SharePointa przez Microsoft Graph — zarówno z aplikacji, jak i z n8n
(oba uwierzytelniają się OAuth-em wymagającym aplikacji/zgody w tenancie). **Nie ma Grapha,
nie ma n8n, nie ma Azure.**

Dostępny kanał: plik jest już **zsynchronizowany lokalnie** przez klienta OneDrive na koncie
użytkownika, na **maszynie włączonej 24h**:

```
C:\Users\<uzytkownik>\OneDrive - <firma>\
    <biblioteka> - Dokumenty\<folder>\Kolejka.xlsx
```

Root `OneDrive - <firma> \ <biblioteka> - Dokumenty` = zsynchronizowana
biblioteka SharePointa (nie prywatny OneDrive), więc edycje innych osób realnie wpadają do
tego lokalnego pliku, a zapis do niego OneDrive wypycha z powrotem na SharePoint.

## Architektura: lokalny agent-watcher

```
Excel na SharePoint  ──OneDrive sync──►  lokalny .xlsx (maszyna 24h, konto użytkownika)
                                                │
                                    lokalny agent (skrypt Python, watcher)
                                                │
   Faza A  Excel→apka:  zmiana pliku → czytaj → POST snapshot → /api/import/sync (Bearer token)
   Faza B  apka→Excel:  pytaj apkę o zmiany → zapisz komórki do .xlsx → OneDrive wypycha w górę
```

Agent to jedyny „kurier". Aplikacja pozostaje serwerem na Coolify/Hetzner; nie zna
SharePointa ani OneDrive — dostaje/oddaje dane wyłącznie przez własne HTTP API.

## Fazowanie (każda faza działa sama)

- **Faza A — Excel → apka (jednokierunkowo).** Agent czyta plik przy zmianie i POST-uje cały
  snapshot na istniejący endpoint. Apka natywnie liczy różnice, aktualizuje, pisze historię,
  powiadamia. Excel nadpisuje swoje kolumny (łącznie ze statusem). **To dowozi widoczność
  zmian z Excela w apce — główną wartość — bez ryzyka zapisu zwrotnego.**
- **Faza B — apka → Excel (dwukierunkowo).** Dochodzi baseline per kontener (three-way merge),
  zapis zwrotny do lokalnego `.xlsx` przez agenta, wykrywanie pętli echa i konfliktów.

Ten dokument szczegółowo specyfikuje **Fazę A**; Fazę B szkicuje na końcu.

---

## Faza A — szczegóły

### Decyzje

1. **Agent = kurier.** Wysyła plik 1:1 na endpoint; żadnej logiki różnic po stronie agenta.
2. **Apka myśli.** Parsuje snapshot, porównuje per numer kontenera, wykrywa różnice,
   aktualizuje, audytuje, powiadamia. Idempotentne: ten sam plik = 0 różnic.
3. **Źródło prawdy = Excel** (Faza A jednokierunkowa): pola z `HEADER_MAP` nadpisywane z
   Excela, łącznie ze statusem (`_derive_status`). Pola tylko-w-apce nietknięte.
4. **Kasowanie poza zakresem** — kontener zniknął z arkusza → tylko log, bez usuwania.

### Komponenty (apka — reuse istniejącej infrastruktury)

| Element | Opis | Status |
|---|---|---|
| `POST /api/import/sync` | Endpoint w `routers/imports.py`: `.xlsx` + `company_code` + token serwisowy → `reconcile_queue`. | nowe |
| `build_container_fields(db, company, raw)` | Wspólny builder pól z wiersza; wyciągnięty z `import_containers`. | refactor (Task 1) |
| `reconcile_queue(...)` | Parsuje (`_parse_rows`), diffuje wobec DB per numer, nadpisuje kolumny Excela, `record()` per pole. | nowe (Task 2) |
| Historia | `record()` per zmienione pole (`note="sync z Excela"`). | jest |
| Powiadomienia | `notify(company_watchers)` per zmieniony kontener z listą pól. | infra jest |
| Auth serwisowy | Token `sync_api_token` w configu, nagłówek `Authorization: Bearer`. | nowe |
| Aktor audytu | Opcjonalne konto `sync_actor_login` (np. `excel-sync`); brak → `user=None`. | nowe (drobne) |

### Komponent — lokalny agent (nowy, osobny deliverable)

- Mały skrypt Python na maszynie 24h. Pilnuje `! Kolejka 2025-2026 Kopiuj.xlsx`
  (watchdog na katalogu albo polling czasu modyfikacji co N sek — polling prostszy i
  odporny na zdarzenia OneDrive).
- Przy zmianie: odczekaj krótką stabilizację (plik dosynchronizowany/zamknięty), wyślij
  `POST multipart` z plikiem na `/api/import/sync?company_code=…` z Bearer tokenem.
- Konfiguracja z pliku/env: ścieżka pliku, URL apki, token, company_code, interwał.
- Log lokalny + prosty backoff przy błędzie sieci. Uruchamiany jako Harmonogram zadań
  Windows (Task Scheduler) na starcie/stale.

### Testy Fazy A

Apka (pytest): seed kontenera → POST zmienionego snapshotu → assert update + AuditLog +
Notification; powtórny POST = 0 zmian (idempotencja). (Szczegóły w planie.)
Agent: test jednostkowy „przy wykrytej zmianie wysyła POST z plikiem" (mock HTTP).

---

## Faza B — szkic (do zaplanowania później)

- **Three-way merge:** apka trzyma per kontener `baseline` = ostatni uzgodniony stan pól.
  Porównanie `baseline` vs `Excel-teraz` vs `apka-teraz`:
  - zmiana tylko w Excelu → update apki;
  - zmiana tylko w apce → zapis zwrotny do Excela (agent);
  - oba zgodne → podnieś baseline;
  - oba różne (konflikt) → **LWW**.
  Podniesienie baseline po uzgodnieniu kasuje **pętlę echa** (wartość zapisana do Excela jest
  już baseline'em i nie wraca jako „zmiana").
- **Konflikt = ostatnia zmiana wygrywa (przybliżenie).** Excel nie ma czasu per komórka —
  używamy czasu modyfikacji CAŁEGO pliku (z systemu plików / OneDrive) jako czasu strony
  Excela, kontra dokładny czas zmiany pola w apce (AuditLog). Przybliżenie na poziomie pliku,
  nie komórki — świadomie zaakceptowane.
- **Zapis zwrotny:** apka wystawia „co zmienić" (kontener→pola→wartości); agent otwiera
  lokalny `.xlsx`, znajduje wiersz po numerze kontenera, kolumnę po nagłówku, zapisuje,
  OneDrive wypycha. Haczyk: plik otwarty w Excelu = blokada/kopie konfliktu OneDrive —
  strategia zapisu (retry gdy zablokowany) do rozstrzygnięcia w planie Fazy B.

## Poza zakresem (świadomie, obie fazy)

- Microsoft Graph / Entra / n8n / Azure — wykluczone ograniczeniem IT.
- Usuwanie kontenerów zniknięć z arkusza.
- Webhook/near-real-time — polling wystarcza na start.
