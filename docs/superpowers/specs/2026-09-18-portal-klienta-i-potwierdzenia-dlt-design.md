# Portal kliencki + potwierdzenia DLT

Data: 2026-09-18 · Status: zatwierdzony w brainstormingu (sesja) · Dostawa: 2 osobne PR-y

## A. Portal kliencki (rozszerzenie publicznego /k/:token)

Decyzje: pozycja statku na mapce, dokumenty do pobrania, branding + PL/EN,
portal wielu kontenerów — wszystko w zakresie.

1. **Dwa typy linków publicznych**:
   - istniejący per-kontener (`/k/:token`) — bez zmian,
   - nowy **link kliencki** per klient: token losowy ≥24 B, w DB SHA-256,
     wygaszalny; strona-portal z listą aktywnych kontenerów klienta
     (nr, status, ETA, data dostawy) → klik = szczegół z osią czasu.
2. **Powiązanie kontener→klient**: po istniejących polach `customer_*` (tranzyty)
   + ręczne przypięcie klienta do kontenera (model Customer/lekki słownik —
   zbadać czy Baza klientów już istnieje; jeśli tak, użyć jej).
3. **Mapka statku** na szczególe: VesselMiniMap z pozycją i trailem statku TEGO
   kontenera; publiczny endpoint zwraca wyłącznie pozycję/trasę jednego statku —
   zero nazw/danych innych ładunków i spółek.
4. **Dokumenty**: checkbox „widoczny dla klienta" per załącznik (domyślnie OFF,
   włącza admin/logistics); portal listuje tylko oznaczone; pobranie przez token;
   audyt pobrań (kto=token, co, kiedy).
5. **Branding + języki**: nagłówek z nazwą/logo firmy (konfigurowalne, bez
   hardkodu spółki), przełącznik PL/EN na stronach publicznych.
6. Bezpieczeństwo: rate-limit publicznych endpointów, 404 jednolite, żadnych
   danych poza zakresem tokenu. Testy izolacji obowiązkowe.

## B. Potwierdzenia DLT (Przygotowane + Wysłane)

Zależność: buduje NA PR „wywołania DLT auta/HU/analityka" (PalletCallTruck).

1. Mail wywołania zawiera tokenowy link (wzorzec driver-links: hash w DB,
   jednolite 404, dezaktywacja po realizacji/wygaszeniu).
2. Strona publiczna: wywołanie tylko-do-odczytu (auta → miejsca → HU/ilości)
   + przyciski **„Przygotowane"** i **„Wysłane"** (sekwencyjnie; idempotencja
   z oknem dedup jak „Przyjechałem" u kierowców).
3. Statusy PalletCall rozszerzone: PRZYGOTOWANE, WYSLANE_Z_DLT; przejścia
   zapisują audyt + dzwonek (notify) dla logistyki i autora wywołania.

## Testy

- A: portal klienta nie widzi cudzych kontenerów (spółki/klienci), dokument bez
  flagi niewidoczny i niepobieralny, endpoint statku nie ujawnia innych statków,
  token wygaszony → 404.
- B: przejścia statusów + idempotencja, token po realizacji nieaktywny,
  powiadomienia wysłane raz.
