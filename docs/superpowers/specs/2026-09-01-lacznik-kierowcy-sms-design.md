# Łącznik kierowcy (SMS + strona dostawy) — design

Data: 2026-09-01 · Status: zatwierdzony przez użytkownika

## Cel

Kierowca wie gdzie i kiedy podjechać bez telefonów do logistyki; magazyn i logistyka
wiedzą, że przyjechał albo że się spóźni. Drugi krok roadmapy (po „Kompletności
dokumentów celnych"; dalej: integracje/automatyzacja → analityka Faza 2).

## Decyzje (z brainstormingu)

1. Kanał: **SMS z unikalnym linkiem** do mobilnej strony kierowcy (bez logowania).
2. Zakres strony: **info o dostawie + przyciski „Przyjechałem" / „Spóźnię się"**
   (samouzupełnianie danych kierowcy i status rozładunku na żywo — odrzucone, YAGNI).
3. Wysyłka: **auto dzień przed dostawą (~15:00) + ręczny przycisk** w panelu kierowcy.

## Zakres

### 1. Bramka SMS (abstrakcja providera)

- Wzorzec trackingu (SafeCube): `SMS_PROVIDER=smsapi|mock|off` w configu
  (pydantic-settings), klucz `SMSAPI_TOKEN` wyłącznie w Coolify.
- Provider produkcyjny: **SMSAPI.pl** (REST). `mock` do dev/testów (zapisuje
  wysyłki w pamięci/logu), `off` → akcje SMS zwracają czytelny błąd konfiguracyjny
  (komunikat dla admina, neutralny dla reszty).
- Model `SmsMessage(id, container_id, phone, body, status, provider_id, error,
  created_at)` — historia wysyłek + status dostarczenia (jeśli provider zwraca).

### 2. Link kierowcy

- Tokenowy, wygasający (wzorzec linków awizo/SENT): `DriverLink(token unique,
  container_id, expires_at)`; ważny do **+2 dni po planowanej dacie dostawy**;
  nowa wysyłka SMS po zmianie kierowcy/daty generuje świeży token, stary wygasa.
- Publiczna trasa `GET /dostawa/{token}` (bez auth) — walidacja tokenu i ważności,
  poza tym 404 (bez rozróżniania „wygasł" vs „nie istnieje" — nie ułatwiamy enumeracji).

### 3. Strona kierowcy (mobile-first, PL/EN)

- Treść: nr kontenera, planowana data dostawy, magazyn (nazwa, adres,
  przycisk „Nawiguj" → link Google Maps), telefon kontaktowy, instrukcje wjazdu.
- Nowe pola magazynu (admin): `address`, `contact_phone`, `entry_instructions`
  (istniejąca zakładka magazynów).
- Akcje:
  - **„Przyjechałem"** → `notify` (dzwonek + istniejące kanały) do magazynu docelowego
    i obserwatorów spółki; bez automatycznej zmiany statusu kontenera.
  - **„Spóźnię się"** + szacowana godzina (select/kolejne pół godziny) → `notify`
    do logistyki i magazynu z godziną.
- Zdarzenia zapisywane w audycie kontenera (`driver-arrived`, `driver-delayed {hh:mm}`);
  każda akcja idempotentna w sensie UX (ponowne kliknięcie = kolejny wpis, bez błędu).

### 4. Wysyłka SMS

- **Auto**: przebieg w istniejącym cyklu alertów, raz dziennie ~15:00 czasu PL —
  kontenery z `delivery_date == jutro` (pole planowanej dostawy), `driver_phone`
  niepuste, brak wcześniejszej udanej wysyłki dla tej daty → SMS z linkiem.
  Dedup per kontener+data (jak `customs-delay`).
- **Ręcznie**: przycisk „Wyślij SMS kierowcy" w `DriverPanel` (role jak edycja
  kierowcy); zawsze generuje świeży link i wysyła.
- Panel kierowcy pokazuje historię: kiedy, na jaki numer, status/błąd.
- Treść SMS (PL, krótko): „TIMPORYE: dostawa {container_no} {data}. Szczegóły
  i potwierdzenie przyjazdu: {link}".

## Poza zakresem

- Samouzupełnianie danych kierowcy przez link.
- Status rozładunku na żywo (czekaj/rampa X/gotowe).
- Sloty godzinowe rozładunków.
- Kanały WhatsApp/Viber.

## Testy (strażnicy regresji)

- Provider `off` → akcje SMS zwracają błąd konfiguracyjny; `mock` rejestruje wysyłkę.
- Token: ważny działa bez auth; wygasły/nieistniejący → 404; nowa wysyłka unieważnia
  stary token.
- Strona kierowcy nie ujawnia danych handlowych (tylko pola z sekcji 3).
- „Przyjechałem"/„Spóźnię się" → powiadomienia do właściwych odbiorców + wpis audytu.
- Auto-wysyłka: tylko jutrzejsze dostawy z telefonem, dedup per kontener+data.
- Dev-shim guard dla nowych kolumn/tabel.
