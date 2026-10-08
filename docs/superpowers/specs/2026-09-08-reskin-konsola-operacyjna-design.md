# Reskin „Konsola operacyjna" (wariant A: stal + bursztyn) — cała aplikacja

Data: 2026-09-08 · Branch: `claude/reskin-konsola-a` · Status: zatwierdzony kierunek (makiety A/B/C, wybrano A)

## Cel

Aplikacja Kolejka wygląda generycznie (domyślny niebieski `#0b5fff`, Segoe UI, karty-mozaika
z miękkimi cieniami i radius 12px). Reskin na styl „konsoli operacyjnej": gęsty, danocentryczny,
przemysłowy — ciemny stalowy chrome, jasny workspace, bursztynowy akcent, mono do danych,
hairline zamiast cieni. Bez zmian logiki, routingu ani struktury danych.

Makieta referencyjna: wariant A z `konsola-mockups.html` (scratchpad sesji) — screenshot
zatwierdzony przez użytkownika.

## 1. Tokeny (`frontend/src/styles.css` `:root`)

| Token | Było | Będzie |
|---|---|---|
| `--bg` | `#f8fafc` | `#f2f4f7` |
| `--panel` | `#ffffff` | `#ffffff` (bez zmian) |
| `--border` | `#e6ecf4` | `#d7dde6` (wyraźniejszy hairline) |
| `--text` | `#1c2733` | `#18202b` |
| `--muted` | `#64748b` | `#5c6a7c` |
| `--accent` | `#0b5fff` | `#f5a623` (bursztyn — wypełnienia, paski, podkreślenia, aktywne stany) |
| `--accent-ink` | (nowy) | `#b97509` (ciemny bursztyn — tekst/linki na jasnym tle; WCAG AA) |
| `--danger` | `#d92d20` | `#c92a1e` |
| `--chrome` | (nowy) | `#10161f` (stalowy nagłówek) |
| `--good` | (nowy) | `#0e8a6a` (wartości OK) |

**Zasada akcentu**: `--accent` (czysty bursztyn) wolno używać tylko na wypełnieniach i na
ciemnym tle. Każde użycie akcentu jako koloru TEKSTU na jasnym tle przechodzi na
`--accent-ink`. Audyt wszystkich obecnych `var(--accent)` w styles.css pod tym kątem
jest częścią implementacji.

Kształt: globalny radius 12px → **3px** (chipy 2px). Cienie kart (`box-shadow`) usunięte;
głębia przez hairline `--border`.

## 2. Typografia

- **Archivo** (700/800) — h1, logo.
- **IBM Plex Sans** (400–700) — tekst podstawowy (zastępuje Segoe UI).
- **IBM Plex Mono** (400–700) — wszystkie dane: numery kontenerów, daty, KPI, zegary,
  etykiety uppercase (`letter-spacing .16–.22em`), wartości liczbowe (`tabular-nums`).
- Instalacja: pakiety `@fontsource/*` (npm), importy w `main.tsx` — bundlowane przez Vite,
  zero runtime-zależności od CDN (prod na Coolify działa offline).

## 3. Chrome (nagłówek)

Tło `--chrome` `#10161f`, dolna krawędź `2px solid var(--accent)`. Logo: Archivo 800 +
podpis „CONTAINER FLOW" mono w bursztynie. Aktywna zakładka: jasny tekst +
`inset 0 -2px 0 var(--accent)`. Zegary Radom/Shanghai i badge licznika: IBM Plex Mono.
Kropka statusu online zostaje.

## 4. Komponenty (restyling istniejących klas)

- **KPI**: z osobnych kart → jeden zwarty pasek (`display:grid`, komórki rozdzielone
  `border-right: 1px solid var(--border)`); wartości mono 30px tabular-nums; wartości
  wiodące zero prezentowane jako `00` tam, gdzie renderuje je frontend jako liczbę —
  **bez zmiany**: formatowanie zostaje jak jest (mockup używał `00` tylko poglądowo).
  Alert „Wymaga uwagi" to komórka paska z tłem `#fdf3f2`, nie osobny box.
  Zmiana markup TYLKO na Pulpicie i Kalendarzu (współdzielone klasy `.kpi*`).
- **Panele**: `.panel-head`/`.mini-title` — mono uppercase, hairline pod spodem, bez cieni.
- **Tabele**: nagłówki mono uppercase 9.5px, kolumny danych (numery, daty) mono,
  paddingi ciaśniejsze (8–9px), zebra zbędna — hairline między wierszami.
- **Chipy statusów**: prostokąt radius 2px, tło `--chrome`, tekst bursztyn, mono 10px.
- **Przyciski**: primary = tło `--accent`, tekst `--chrome`, radius 3px; secondary =
  hairline border na `--panel`.
- **Paski postępu**: wypełnienie `--accent`; stan „dobry" `--good`.

## 5. Wiersze kolejki wg magazynu (DLT / ACME)

Pastelowe pełne tła zastąpione wzorcem **krawędź + tinta**:

- DLT: `border-left: 3px solid #d6247a` (magenta ładunkowa) + tło `rgba(214,36,122,.04)`
- ACME: `border-left: 3px solid #12a150` (zieleń sygnałowa) + tło `rgba(18,161,80,.04)`

Tokeny `--row-dlt`/`--row-acme` (+ `-border`) przemapowane na nowe wartości — miejsca
użycia w komponentach bez zmian, o ile stosują tokeny. Kolor niesie krawędź, nie tło:
czytelny peryferyjnie, ekran z 50 wierszami nie „tęczuje".

## 6. Motywy zakładek (mięta / piasek / stal — `.mod-acme` itd.)

Mechanizm kaskady zostaje. Odcienie skorygowane, by grały ze stalowym chrome:
tła bledsze (bliżej `--bg`), akcenty modułów przygaszone; `--accent-ink` per moduł.
Dokładne wartości dobrane przy implementacji z weryfikacją kontrastu AA.

## 7. Bez zmian

- Struktura React, routing, logika, API, dane.
- Semantyka ról i uprawnień.
- Formatowanie liczb/dat renderowane przez frontend.

## 8. Zakres plików

- `frontend/src/styles.css` — główna praca (tokeny + komponenty).
- `frontend/src/main.tsx` (lub entry) — importy @fontsource.
- `frontend/package.json` — 3 pakiety fontów.
- Markup KPI: komponenty Pulpitu i Kalendarza (tylko struktura paska KPI).

## 9. Weryfikacja

1. Screenshot każdej głównej strony (Pulpit, Kolejka, Kalendarz, Agencja celna, panele
   Operacje/Logistyka/Analiza/Administracja) przed → po; porównanie z makietą A.
2. Kontrast WCAG AA na parach tekst/tło (w szczególności bursztyn: tylko `--accent-ink`
   na jasnym tle).
3. Frontend build (`vite build`) bez błędów; istniejące testy repo zielone.
4. Wiersze DLT/ACME rozróżnialne na liście kolejki przy pełnej tabeli.

## 10. Ryzyka

- Bursztyn jako tekst na białym — pilnowane zasadą `--accent-ink` (pkt 1).
- Miejsca z zahardkodowanymi kolorami poza tokenami (np. `#94a3b8` w `.kpi-label`) —
  implementacja obejmuje przegląd styles.css i podpięcie ich pod tokeny tam, gdzie dotyczy
  reskinu; bez refaktoru niezwiązanych miejsc.
- Motywy modułów: ryzyko zgrzytu kolorystycznego — weryfikacja wizualna per zakładka.
