# UX Foundations — cała aplikacja: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Cała aplikacja dobrze prowadzi użytkownika (H3/H5/H10), dobrze wygląda w stanach przejściowych (H1/H8) i pokazuje trackingi/świeżość danych (H1) — wg audytu `docs/audyt-nielsen-kolejka.md` i mapy `docs/mapa-procesow-szczegolowa.md`.

**Architecture:** Frontend-first (`frontend/src`), wspólne prymitywy zamiast łatek per widok: jeden system toastów, jeden skeleton, jeden stan błędu z retry, jeden tooltip pomocy. Backend tylko tam, gdzie brakuje danych (nic nie zapowiada takiej potrzeby — `tracked_at` już jest w API). Każdy task = osobny commit + testy.

## Global Constraints
- i18n ×3 (pl/en/pt) dla każdego nowego tekstu; Polish-first.
- Wspólne prymitywy w `frontend/src/components.tsx` (lub obok) — ZERO duplikowania per strona.
- Style przez istniejące zmienne CSS; żadnych nowych bibliotek.
- Testy: `npx tsc --noEmit` + pełne `npx vitest run` (foreground) po każdym tasku; strażnik CSS na nowe klasy (lekcja dead-class).
- Nie zmieniać kontraktów API.

---

### Task 1: Warstwa feedbacku — toasty, skeletony, błąd+retry (H1/H9)
**Files:** Create `frontend/src/feedback.tsx` (ToastProvider + useToast, `<Skeleton rows={n}/>`, `<LoadError onRetry/>`); Modify `frontend/src/api.ts` (nic w kontrakcie — tylko eksport `errorMessage` jeśli brak), `App.tsx` (provider), `styles.css`, `i18n.ts`. Test: `feedback.dom.test.tsx`.
Zakres podłączenia (w tym tasku tylko 3 najcięższe widoki, reszta w Task 4): `QueuePage` (lista: skeleton przy load, LoadError z retry przy fail; toast po: przeniesieniu daty, zmianie magazynu, eksporcie), `ContainerPage` (toast po zapisie klienta/statusu), `ForwardingPage` (toast po akcjach zlecenia).
TDD: test — toast pojawia się i znika, LoadError renderuje przycisk i woła onRetry, skeleton widoczny przy pending. Commit: `feat(ux): wspólna warstwa feedbacku — toasty, skeletony, błąd z retry`.

### Task 2: Guardraile statusów (H5/H3)
**Files:** Modify `frontend/src/pages/QueuePage.tsx` i/lub `ContainerPage.tsx` (miejsce zmiany statusu głównego), `components.tsx`, `i18n.ts`. Test: `status.guard.dom.test.tsx`.
Reguła (frontend-only, backend bez zmian): kolejność `CONTAINER_STATUSES` = oś czasu; wybór statusu WCZEŚNIEJSZEGO niż obecny → modal ostrzeżenia „Cofasz status z X na Y — to nietypowe. Kontynuować?" (z polem na notatkę, która idzie w istniejące `note` audytu). Ruch w przód — bez zmian. Analogicznie ostrzeżenie przy `customs_status` cofanym z ODPRAWIONY.
TDD: ruch w przód bez modala; ruch wstecz pokazuje modal; anuluj = brak requestu; potwierdź = request z notatką. Commit: `feat(ux): ostrzeżenie przy cofaniu statusu (kontener + odprawa)`.

### Task 3: Pomoc kontekstowa + trackingi świeżości (H10/H1)
**Files:** Create `frontend/src/HelpTip.tsx` (ikona „?" + popover, wzorzec useDismiss); Modify `QueuePage.tsx`, `TrackingPage.tsx`, `i18n.ts`, `styles.css`. Test: `helptip.dom.test.tsx`.
Pomoc „?" przy: limicie dziennym (jak liczony: tylko POTWIERDZONE, bez tranzytów), cyklu potwierdzania daty (PROPOZYCJA→WYSLANE→POTWIERDZONE), zakładce Tranzyt (co to jest), sekcji odprawy (obieg z agencją). Teksty 2-3 zdania, z audytu/mapy procesów.
Trackingi: w wierszu/szczegółach kontenera wskaźnik świeżości `tracked_at` („sync 2 h temu" / „nigdy"; >24 h = przygaszony z ⚠). Relatywny czas: prosty helper (minuty/godziny/dni), bez bibliotek.
Commit: `feat(ux): pomoc kontekstowa + wskaźnik świeżości trackingu`.

### Task 4: Rollout feedbacku na resztę modułów + porządki (H1/H4/H8)
**Files:** Modify pozostałe strony z fetch+akcjami: `CustomsPage/ComplaintsPage/AdminPanel/TrackingPage/AvizoFormPage` (nazwy zweryfikować w `frontend/src/pages/`), `i18n.ts`. Test: rozszerzenie `feedback.dom.test.tsx` o 1 przypadek reprezentatywny.
Zakres: każdy widok listy dostaje skeleton+LoadError; każda akcja zapisu toast; przy okazji unifikacja czyszczenia filtrów w kolejce (jeden mechanizm „Wyczyść wszystkie", stary przycisk usunięty — minor z review #204) i okrojona karta mobile z etykietami (fast-follow z #204: `.cont-card` pokazuje TYLKO nr/dostawcę/statusy/datę + etykiety pól).
Commit: `feat(ux): feedback we wszystkich modułach + karta mobile + unifikacja filtrów`.

## Poza zakresem
Maszyna stanów po stronie backendu (graf przejść jak ORDER_FLOW) — osobna decyzja/plan; frontendowe ostrzeżenie z Task 2 to pierwszy krok. Skróty klawiszowe (H7 nice-to-have). Historia wyszukiwań (H6).
