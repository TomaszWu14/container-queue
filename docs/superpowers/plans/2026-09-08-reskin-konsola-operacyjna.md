# Reskin „Konsola operacyjna" (stal + bursztyn) — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reskin całej aplikacji Kolejka na styl konsoli operacyjnej (wariant A ze specu): stalowy chrome + bursztynowy akcent + IBM Plex/Archivo + hairline zamiast cieni — bez zmian logiki, routingu i danych.

**Architecture:** Praca prawie wyłącznie w `frontend/src/styles.css` (token-driven CSS — `:root` + komponenty). Fonty przez `@fontsource` importowane w `main.tsx`. Pasek KPI realizowany czystym CSS (grid `gap:0` + separator), zero zmian markup w React.

**Tech Stack:** React 18 + Vite + vitest (istniejące `*.dom.test.tsx` muszą zostać zielone). Spec: `docs/superpowers/specs/2026-09-08-reskin-konsola-operacyjna-design.md`.

## Global Constraints

- Czysty bursztyn `#f5a623` (`--accent`) NIGDY jako `color:` na jasnym tle — tam zawsze `--accent-ink: #b97509`. Na ciemnym tle (`--chrome`) czysty bursztyn OK.
- Zero nowych zależności poza trzema pakietami `@fontsource/*`.
- Bez zmian w komponentach React poza `main.tsx` (importy fontów). Wyjątek: brak.
- Tła wierszy DLT/ACME to informacja operacyjna — muszą pozostać rozróżnialne (nowy wzór: krawędź 3px + tinta 4%).
- Wszystkie komendy uruchamiane z `frontend/`: `npm run typecheck`, `npm test`, `npm run build`.
- Weryfikacja wizualna: `npm run dev` (vite, port 5173) albo zbudowany frontend na :8000 — screenshot po każdym tasku.
- Commity atomowe per task, prefiks `feat(ux):` lub `style(design):`.

---

### Task 0: Branch

**Files:** brak zmian plików.

- [ ] **Step 1: Utwórz branch od bieżącego HEAD** (zawiera dedupe .kpi i spec):

```bash
git checkout -b claude/reskin-konsola-a
```

---

### Task 1: Fonty (@fontsource)

**Files:**
- Modify: `frontend/package.json` (3 pakiety)
- Modify: `frontend/src/main.tsx` (importy przed `./styles.css`)
- Modify: `frontend/src/styles.css:21` (font-family w `:root`)

**Interfaces:**
- Produces: rodziny `'Archivo'`, `'IBM Plex Sans'`, `'IBM Plex Mono'` dostępne globalnie; kolejne taski ich używają po tych dokładnych nazwach.

- [ ] **Step 1: Zainstaluj pakiety**

```bash
cd frontend
npm install @fontsource/archivo @fontsource/ibm-plex-sans @fontsource/ibm-plex-mono
```

- [ ] **Step 2: Importy w `main.tsx`** — dodaj PRZED `import './styles.css'`:

```tsx
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-sans/700.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/600.css'
import '@fontsource/ibm-plex-mono/700.css'
import '@fontsource/archivo/700.css'
import '@fontsource/archivo/800.css'
```

- [ ] **Step 3: Podmień font-family w `:root`** (styles.css:21):

```css
  font-family: 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif;
```

Dodaj też token mono (w `:root`, obok):

```css
  --font-mono: 'IBM Plex Mono', ui-monospace, Consolas, monospace;
```

- [ ] **Step 4: Podepnij wszystkie użycia mono pod token.** W styles.css zamień KAŻDE `font-family: ui-monospace, Consolas, monospace` na `font-family: var(--font-mono)` (linie: 781, 885, 893, 900, 904, 923, 929 — zweryfikuj grepem `ui-monospace`).

- [ ] **Step 5: Weryfikacja**

```bash
npm run typecheck && npm test && npm run build
```

Expected: PASS wszystkie. Otwórz app, sprawdź w devtools, że body ma IBM Plex Sans.

- [ ] **Step 6: Commit**

```bash
git add package.json package-lock.json src/main.tsx src/styles.css
git commit -m "feat(ux): fonty konsoli — IBM Plex Sans/Mono + Archivo przez @fontsource"
```

---

### Task 2: Tokeny + kształt (radius/cienie) + audyt akcentu

**Files:**
- Modify: `frontend/src/styles.css` (`:root` linie 8–21 + sweep całego pliku)

**Interfaces:**
- Produces: tokeny `--accent: #f5a623`, `--accent-ink: #b97509`, `--chrome: #10161f`, `--good: #0e8a6a`; wszystkie kolejne taski z nich korzystają.

- [ ] **Step 1: Podmień wartości w `:root`**

```css
:root {
  --bg: #f2f4f7;
  --panel: #ffffff;
  --border: #d7dde6;
  --text: #18202b;
  --muted: #5c6a7c;
  --accent: #f5a623;       /* bursztyn: wypełnienia, paski, aktywne stany, ciemne tło */
  --accent-ink: #b97509;   /* bursztyn tekstowy: color: na jasnym tle (WCAG AA) */
  --chrome: #10161f;       /* stalowy nagłówek */
  --good: #0e8a6a;
  --danger: #c92a1e;
  /* wiersze wg magazynu: krawędź + tinta (Task 5) */
  --row-dlt: rgba(214, 36, 122, 0.04);   --row-dlt-border: #d6247a;
  --row-acme: rgba(18, 161, 80, 0.04);  --row-acme-border: #12a150;
  --banner-bg: #f7f9fb;   --banner-border: #e3e8ef;  --banner-ink: var(--muted);
  --soft: #eceff4;
  --accent-soft: #fdf3e0; /* tinta bursztynu na zaznaczenia */
  --band: #ffffff;        --band-border: #d7dde6;
  font-family: 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', ui-monospace, Consolas, monospace;
}
```

- [ ] **Step 2: Audyt akcentu jako tekstu.** Grep `color:` + `var(--accent)` po całym pliku (~15 miejsc, m.in. linie 135, 258, 319, 338, 342, 353, 399, 427, 572). Każde `color: var(--accent)` na jasnym tle → `color: var(--accent-ink)`. `border-color: var(--accent)` i `background: var(--accent)` zostają. `accent-color` (checkbox, linia 67) zostaje.

- [ ] **Step 3: Kształt.** Sweep pliku:
- `border-radius: 12px` (8 wystąpień) → `border-radius: 3px`
- `border-radius: 7px`/`6px`/`8px`/`10px` na panelach/przyciskach/inputach → `3px`; na chipach/badge'ach → `2px`; `border-radius: 50%` (kropki, avatary) zostaje; pigułki celowo okrągłe (np. `.badge` licznika w nav) → `2px`.
- `box-shadow` na kartach/panelach (64 wystąpienia — przejrzyj każde): dekoracyjne cienie kart USUŃ; zostaw cienie funkcyjne: focus-ring (linia 66), dropdowny/menu kontekstowe/modale (elementy floating muszą się odcinać od tła), sticky topbar może zostać z subtelnym.

- [ ] **Step 4: Weryfikacja**

```bash
npm run typecheck && npm test
```

Expected: PASS. Screenshot Pulpitu — tło chłodniejsze, borders ostrzejsze, akcent bursztynowy na przyciskach.

- [ ] **Step 5: Commit**

```bash
git add src/styles.css
git commit -m "feat(ux): tokeny konsoli operacyjnej — stal+bursztyn, radius 3px, hairline zamiast cieni"
```

---

### Task 3: Chrome (topbar)

**Files:**
- Modify: `frontend/src/styles.css:69-86` (blok `.topbar`)

- [ ] **Step 1: Restyle `.topbar`**

```css
.topbar {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  background: var(--chrome); color: #fff; padding: 10px 20px;
  position: sticky; top: 0; z-index: 60;
  border-bottom: 2px solid var(--accent);
}
.topbar .brand { font-family: 'Archivo', sans-serif; font-weight: 800; letter-spacing: 0.04em; }
.topbar a {
  color: #9aa7b8; text-decoration: none; padding: 6px 11px; border-radius: 3px;
  display: inline-flex; align-items: center; gap: 6px; font-weight: 600;
}
.topbar a.active, .topbar a:hover { background: rgba(255,255,255,0.07); color: #fff; }
.topbar a.active { box-shadow: inset 0 -2px 0 var(--accent); }
.topbar .user { font-size: 0.85rem; color: #c7d2e0; }
.topbar button { background: none; border: 1px solid #3a4656; color: #c7d2e0; border-radius: 3px; padding: 5px 10px; }
```

(Zachowaj pozostałe selektory `.topbar *` niewymienione wyżej; zmień tylko wartości kolorów `#10263f`/`#1d3c5f`/`#3b5876` na powyższe.)

- [ ] **Step 2: Zegar i badge licznika na mono.** W blokach `.worldclock` i badge licznika nav dodaj `font-family: var(--font-mono)`; kolory zegara: etykiety `#68758a`, cyfry `#c7d2e0`.

- [ ] **Step 3: Weryfikacja** — `npm test`; screenshot: ciemna stal, bursztynowa linia, aktywna zakładka podkreślona.

- [ ] **Step 4: Commit**

```bash
git add src/styles.css
git commit -m "feat(ux): chrome konsoli — stalowy topbar z bursztynowym podkreśleniem"
```

---

### Task 4: KPI-pasek + panele + typografia danych

**Files:**
- Modify: `frontend/src/styles.css` (`.dash-kpis:880`, `.kpi*:881-886`, `.cal-kpis:~1305`, `.mini-title:895`, nagłówki paneli, `.panel-head` jeśli jest)

- [ ] **Step 1: Scal KPI w pasek (CSS-only)**

```css
.dash-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0; border: 1px solid var(--border); border-radius: 3px; overflow: hidden; background: var(--panel); }
.cal-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0; border: 1px solid var(--border); border-radius: 3px; overflow: hidden; background: var(--panel); margin-bottom: 16px; }
.kpi { padding: 14px 18px; background: var(--panel); border: 0; border-right: 1px solid var(--border); border-radius: 0; box-shadow: none; }
.dash-kpis .kpi:last-child, .cal-kpis .kpi:last-child { border-right: 0; }
.kpi:hover { border-color: var(--border); box-shadow: none; }
.kpi-label { font-family: var(--font-mono); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: var(--muted); }
.kpi-value { font-family: var(--font-mono); font-size: 1.9rem; font-weight: 700; line-height: 1.05; margin-top: 8px; font-variant-numeric: tabular-nums; }
.kpi-unit { font-size: 0.78rem; color: var(--muted); }
.mini-title { font-family: var(--font-mono); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: var(--muted); margin-bottom: 10px; }
```

Uwaga: `.kpi-label`/`.mini-title` miały hardcode `#94a3b8` — po zmianie `--muted` jest ciemniejszy (kontrast AA na małym uppercase).

- [ ] **Step 2: Panel „Wymaga uwagi"** (Pulpit, prawa kolumna): znajdź jego klasy w `DashboardPage.tsx` ok. linii 210–225 i odpowiadający CSS; ustaw tło `#fdf3f2`, hairline `--border`, radius 3px, bez cienia; wartość liczbowa mono.

- [ ] **Step 3: Weryfikacja** — `npm test` (w szczególności `app.dom.test.tsx` — Pulpit) PASS; screenshot Pulpitu i Kalendarza: KPI jako jeden zwarty pasek z separatorami.

- [ ] **Step 4: Commit**

```bash
git add src/styles.css
git commit -m "feat(ux): KPI jako zwarty pasek konsoli, panele hairline, mono na danych"
```

---

### Task 5: Tabele, chipy, przyciski, wiersze DLT/ACME

**Files:**
- Modify: `frontend/src/styles.css` (bloki `table.grid`, `.chip`/badge statusów, `.btn`/przyciski, style wierszy używające `--row-dlt`/`--row-acme`)

- [ ] **Step 1: Tabele.** Nagłówki `th`: `font-family: var(--font-mono); font-size: 0.6rem; font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase; color: var(--muted);`. Komórki danych już mają klasę `.mono` — dziedziczą token z Task 1. Paddingi `td` zmniejsz o ~2px jeśli obecnie >10px.

- [ ] **Step 2: Chipy statusów.** Znajdź klasę chipa statusu (np. `W TRANSPORCIE` na Pulpicie — grep `TRANSPORCIE`/`status-chip`/`badge` w styles.css): `border-radius: 2px; background: var(--chrome); color: var(--accent); font-family: var(--font-mono); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.08em;`. Chipy semantyczne (danger/success) zachowują swoje kolory, tylko kształt 2px.

- [ ] **Step 3: Przyciski.** Primary: `background: var(--accent); color: var(--chrome); border-color: var(--accent); font-weight: 700;`. Secondary/ghost: hairline `--border` na `--panel`, tekst `--text`.

- [ ] **Step 4: Wiersze DLT/ACME — krawędź + tinta.** Tokeny już przemapowane w Task 2. Znajdź selektory używające `var(--row-dlt)`/`var(--row-acme)` (tylko styles.css) i upewnij się, że wzór to:

```css
tr.row-dlt td:first-child { box-shadow: inset 3px 0 0 var(--row-dlt-border); }
tr.row-dlt { background: var(--row-dlt); }
tr.row-acme td:first-child { box-shadow: inset 3px 0 0 var(--row-acme-border); }
tr.row-acme { background: var(--row-acme); }
```

(Dokładne selektory dopasuj do istniejących — `inset box-shadow` zamiast `border-left`, bo `border-left` na `tr` nie działa w każdej przeglądarce przy `border-collapse`.)

- [ ] **Step 5: Weryfikacja** — `npm test` PASS (zwłaszcza `queue.rows.dom.test.tsx`); screenshot Kolejki z wierszami obu magazynów: 3px krawędź magenta/zieleń, tło prawie białe, rozróżnialne z daleka.

- [ ] **Step 6: Commit**

```bash
git add src/styles.css
git commit -m "feat(ux): tabele/chipy/przyciski konsoli + wiersze DLT/ACME krawędź+tinta"
```

---

### Task 6: Motywy zakładek (mięta/piasek/stal) + nagłówki stron

**Files:**
- Modify: `frontend/src/styles.css` (bloki `.mod-acme` itd., ~linie 23–60; nagłówki `h1`/page-header)

- [ ] **Step 1: h1 na Archivo.** Globalnie: `h1 { font-family: 'Archivo', sans-serif; font-weight: 700; letter-spacing: -0.01em; }` (dopasuj do istniejącego selektora nagłówka strony).

- [ ] **Step 2: Motywy modułów.** W każdym bloku `.mod-*`: tła zbliż do nowego `--bg` (np. mięta `#f2f9f5` → `#f3f7f5`), nasycenie bannerów zmniejsz ~30%, dodaj `--accent-ink` per moduł (ciemniejsza wersja akcentu modułu przechodząca AA na jasnym tle; np. dla mięty `--accent-ink: #0b6e55`). Akcent modułu w wypełnieniach zostaje.

- [ ] **Step 3: Weryfikacja** — screenshot zakładki z motywem (np. moduł Acme): motyw rozpoznawalny, ale spójny ze stalowym chrome; `npm test` PASS.

- [ ] **Step 4: Commit**

```bash
git add src/styles.css
git commit -m "feat(ux): motywy zakładek dostrojone do konsoli + Archivo w nagłówkach"
```

---

### Task 7: Weryfikacja końcowa

**Files:** brak nowych zmian (poprawki z przeglądu dozwolone).

- [ ] **Step 1: Pełny pipeline**

```bash
cd frontend && npm run typecheck && npm test && npm run build
```

Expected: PASS / PASS / build bez błędów.

- [ ] **Step 2: Przegląd wizualny wszystkich stron.** Screenshot: Pulpit, Kolejka, Kalendarz, Agencja celna (CustomsPage), Zlecenia (OrdersPage), Spedycja (ForwardingPage), Analityka, Administracja, Login. Dla każdej sprawdź: brak niebieskiego `#0b5fff`, brak Segoe UI, brak radius 12px, brak dekoracyjnych cieni, bursztyn-tekst tylko w wersji `--accent-ink`.

- [ ] **Step 3: Kontrast.** Sprawdź pary: `--accent-ink` na `--panel` (4.6:1 ✓), `--muted` na `--panel`, chip bursztyn na `--chrome`. Narzędzie: devtools lub dowolny checker.

- [ ] **Step 4: Commit poprawek (jeśli były) i push**

```bash
git push -u origin claude/reskin-konsola-a
```

PR na `main` z podsumowaniem przed→po (screenshoty).
