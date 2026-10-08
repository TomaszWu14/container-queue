# Moduł reklamacyjny — dokumentacja

Zgłaszanie problemów i reklamacji przy dostawach (kontenerach), ze zdjęciami,
powiadomieniami do magazyniera oraz obiegiem reklamacji do spedycji/ubezpieczyciela
z licznikiem czasu i przypomnieniami.

## Role i uprawnienia

| Akcja | admin | logistyka | magazyn | spedytor |
|---|:--:|:--:|:--:|:--:|
| Utworzenie zgłoszenia/reklamacji, dodanie zdjęć | ✅ | ✅ | ✅ | — |
| Zgłoszenie problemu do magazyniera | ✅ | ✅ | ✅ | — |
| Wysłanie reklamacji do spedycji/ubezpieczyciela | ✅ | ✅ | — | — |
| Zmiana statusu (odpowiedź / zamknięcie) | ✅ | ✅ | — | — |
| Definiowanie listy problemów i ustawień | ✅ | — | — | — |
| Podgląd (w zakresie swoich dostaw) | ✅ | ✅ | ✅ | ✅ |

Reklamacje są widoczne tylko dla dostaw w zakresie użytkownika (separacja spółek
i magazynów obowiązuje tak samo jak w kolejce).

## Zgłoszenie z telefonu (magazynier / logistyk)

1. Zaloguj się w aplikacji webowej na telefonie.
2. Wejdź w dostawę (Kolejka → kafelek → **Szczegóły**).
3. W panelu **Reklamacje** kliknij **„Zgłoś problem / reklamację”**.
4. Wybierz typ: **Zgłoszenie problemu** lub **Reklamacja**.
5. Zaznacz problemy z listy (np. *Uszkodzony kontener*, *Spóźniony kontener*),
   dodaj opis i komentarz do kierowcy.
6. Dołącz zdjęcia: **📷 Zrób zdjęcie** (uruchamia aparat telefonu) lub
   **🖼 Z galerii** (załącznik).
7. Zostaw zaznaczone **„Zgłoś od razu do magazyniera”**, aby powiadomić magazyn.
8. **Zapisz zgłoszenie**.

Po zapisaniu magazynier przypisany do magazynu dostawy dostaje powiadomienie:
w aplikacji (dzwonek), **e-mailem** oraz na **Teams** (jeśli skonfigurowany webhook).

## Numer reklamacji

Format: `PREFIKS-NRKONTENERA-RRRRMMDD` (np. `REK-MRSU9452203-20260708`).
Przy kilku reklamacjach tego samego kontenera w jednym dniu dochodzi sufiks
`-2`, `-3`… — numer jest zawsze unikalny. Prefiks (domyślnie `REK`) zmienia się
w panelu admina.

## Obieg reklamacji i statusy

`NOWA → ZGŁOSZONA → WYSŁANA → ODPOWIEDŹ → ZAMKNIĘTA`

- **ZGŁOSZONA** — wysłano powiadomienie do magazyniera.
- **WYSŁANA** — reklamacja wysłana e-mailem do spedycji lub ubezpieczyciela
  (z numerem, listą problemów, opisem i informacją o zdjęciach). Od tego momentu
  liczony jest czas do przypomnień.
- **ODPOWIEDŹ** — zaznaczasz po otrzymaniu odpowiedzi (zatrzymuje przypomnienia).
- **ZAMKNIĘTA** — sprawa zakończona; trafia do **Archiwum reklamacji**.

## Licznik czasu i przypomnienia

Reklamacje w statusie **WYSŁANA** są monitorowane w tle (co 6 h). Gdy od wysyłki
minie kolejny **próg dni** (domyślnie **15** i **30**), a nie zaznaczono odpowiedzi,
system wysyła przypomnienie do logistyki (in-app + e-mail + Teams): *„Reklamacja …:
brak odpowiedzi od N dni — sprawdź status / czy odpowiedź nie przyszła innym kanałem”*.
Każdy próg strzela raz.

## Panel administratora

**Administracja → Problemy dostaw** — lista wybieralnych problemów (dodawanie,
dezaktywacja). Domyślnie zasiane: uszkodzony/nieposprzątany/spóźniony kontener,
uszkodzony towar, braki w dostawie, zła plomba, zawilgocony towar, dokumenty,
uwagi do kierowcy.

**Administracja → Ustawienia**:
- **Przypomnienia (dni)** — progi po przecinku, np. `15,30`.
- **E-mail ubezpieczyciela** — domyślny adres do reklamacji ubezpieczeniowych.
- **Prefiks numeru reklamacji** — np. `REK`.

## Wymagana konfiguracja (produkcja)

- **E-maile**: `SMTP_HOST` (np. `smtp.office365.com`), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`.
- **Teams**: `TEAMS_WEBHOOK_URL` (webhook kanału). Bez niego powiadomienia idą tylko
  w aplikacji i e-mailem.
- **Zdjęcia** trafiają do wolumenu `uploads` (limit rozmiaru: `MAX_UPLOAD_MB`).

## API (skrót)

| Metoda / ścieżka | Opis |
|---|---|
| `GET /api/complaints?container_id=&status=&archived=` | lista (zakres użytkownika) |
| `POST /api/complaints` | utworzenie (kind, opis, problemy, `report_to_warehouse`) |
| `GET /api/complaints/{id}` | szczegóły + zdjęcia |
| `POST /api/complaints/{id}/photos` | upload zdjęcia (aparat/plik) |
| `GET /api/complaint-photos/{id}/download` | pobranie zdjęcia |
| `POST /api/complaints/{id}/report` | zgłoszenie do magazyniera |
| `POST /api/complaints/{id}/send` | wysyłka do spedycji/ubezpieczyciela |
| `POST /api/complaints/{id}/status` | zmiana statusu |
| `GET/POST/PATCH /api/problem-types` | słownik problemów (admin) |
| `GET/PUT /api/settings` | ustawienia przypomnień (admin) |
