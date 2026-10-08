# Claude w GitHubie: `@claude` i automatyczne konflikty

## Stan faktyczny — obecnie NIE działa (sprawdzone 2026-09-28, audyt DOC-008)
- Oba workflowy (`claude.yml`, `claude-conflicts.yml`) chodzą na runnerze GitHuba `ubuntu-latest`.
  Joby na runnerach GitHuba nie startują — rozliczenia konta GitHub są zablokowane (audyt COST-001;
  adnotacja joba: „The job was not started because recent account payments have failed or your
  spending limit needs to be increased”, job 107693844771). Pozostałe workflowy (poza ręcznym
  `e2e.yml`) chodzą na self-hosted (`[self-hosted, linux]`); te dwa celowo nie — agent z prawem
  zapisu nie chodzi na serwerze.
- Historia przebiegów: `claude-conflicts.yml` — 18, żaden udany (6× `push` = `failure` po 3–5 s,
  bez kroków; 12× `issue_comment` = `skipped` — warunek joba niespełniony).
  `claude.yml` — 12, wszystkie `skipped` (warunek joba niespełniony).
- Nawet po odblokowaniu: merge robiony przez auto-merge (`automerge.yml`, `GITHUB_TOKEN`) **nie**
  wyzwala workflowów, więc „po każdym pushu do `main`” oznacza tylko merge wykonany przez człowieka.
  Dlatego było tylko 6 przebiegów `push` przy ok. 200 PR-ach scalonych od dodania workflowu.

**Co robić dziś:** konflikt z `main` rozwiązujesz sam (albo w lokalnej sesji Claude Code):
`git fetch origin main && git merge origin/main` (merge, nie rebase), rozwiązanie, testy, push.
Pliki i18n mają `merge=union` (`.gitattributes`), więc równoległe dopiski kluczy zwykle łączą się same.

**Decyzja właściciela (P-104):** uregulować płatności GitHub **albo** świadomie przenieść te dwa
workflowy na self-hosted runner **albo** je usunąć. Dopóki jej nie ma, opis niżej to projekt, nie stan.

## Jednorazowa konfiguracja (admin repo)
1. Zainstaluj aplikację **Claude** na repo: https://github.com/apps/claude
   (albo w terminalu `claude` → `/install-github-app`, który zrobi to razem z sekretem).
2. Dodaj sekret w *Settings → Secrets and variables → Actions* — **jeden** z:
   - `ANTHROPIC_API_KEY` — klucz z console.anthropic.com (płatność za tokeny),
   - `CLAUDE_CODE_OAUTH_TOKEN` — z subskrypcji Claude: w terminalu `claude setup-token`.
3. Joby chodzą na runnerach GitHuba (`ubuntu-latest`), nie na serwerze self-hosted — wymagają
   aktywnych rozliczeń GitHub Actions (patrz wyżej).

## `@claude` (`.github/workflows/claude.yml`) — gdy joby startują
Komentarz w PR / issue / review zawierający `@claude …`. Przykłady:
- `@claude zrób review tego PR pod kątem bezpieczeństwa i CLAUDE.md`
- `@claude CI jest czerwone — napraw` (czyta logi Actions, poprawia, pushuje do gałęzi PR)
- `@claude zmień nazwę X na Y i dodaj test`
- w issue: `@claude zaimplementuj to` → gałąź z kodem + link do utworzenia PR
Wywołać może tylko osoba z prawem zapisu. Claude **nie merguje gałęzi** (tak działa akcja) —
od tego jest workflow poniżej.

## Konflikty z `main` (`.github/workflows/claude-conflicts.yml`) — gdy joby startują
- **Automatycznie** po pushu do `main` wykonanym przez człowieka (nie przez auto-merge — patrz wyżej):
  otwarte, nie-draft PR-y w konflikcie dostają merge `origin/main` (merge commit, bez
  rebase/force-push). Znaczniki konfliktu rozwiązuje Claude, workflow sprawdza, że żadne nie zostały,
  pushuje i odpala CI → Auto-merge jak zwykle.
- **Ręcznie**: komentarz `/konflikty` w PR, albo *Actions → Claude — konflikty z main → Run
  workflow* (numer PR).
- `frontend/package-lock.json` i `graphify-out/*` biorą wersję z `main` (lockfile jest potem
  regenerowany, gdy zmienił się `package.json`).
- Nie wyszło → komentarz w PR i etykieta `konflikt-recznie`; kolejne pushe do main nie
  ponawiają prób, dopóki ktoś nie napisze `/konflikty`.

## Koszt
Minuty GitHub Actions (runner `ubuntu-latest`) + tokeny Claude za każde wywołanie.
