# E2E Playwright (plaster 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dowieźć pierwszy zestaw testów E2E (auth per rola, izolacja multi-company, edycja + walidacja ISO 6346) rozwijając istniejący setup `@playwright/test`.

**Architecture:** Playwright uruchamia realny stack (uvicorn FastAPI na SQLite `e2e.db` + `vite dev`). `globalSetup` sieje przez REST admina firmy/userów/kontenery i zapisuje `e2e/.seed.json`. Testy logują się utworzonymi userami i asertują scoping po `company_id`.

**Tech Stack:** TypeScript, `@playwright/test` ^1.63, FastAPI backend (tło), vite dev server.

## Global Constraints

- Runner E2E: **wyłącznie** TypeScript `@playwright/test`. Nie dodawać Python/pytest E2E.
- `baseURL` frontendu: `http://localhost:5173`. Backend REST: `http://localhost:8000`.
- `fullyParallel: false` — wspólna baza, testy serial.
- Selektory: `data-testid` tylko na `ContainerFormModal`; reszta po unikalnym numerze kontenera / URL.
- Hasło E2E userów: podawane jawnie w `POST /api/users` (`password`, ≥8 zn., `send_invite:false`). Nie polegać na `temp_password`.
- Numery kontenerów (ISO 6346, zweryfikowane): firma A = `MSDU0806613`, firma B = `TCLU1234568`, błędny (zła cyfra kontrolna) = `MSDU0806615`.
- Nie modyfikować kodu produkcyjnego poza dodaniem `data-testid` w `ContainerFormModal`.

---

## File Structure

```
frontend/
  playwright.config.ts          # MODIFY: globalSetup, trace/screenshot/video, outputDir
  .gitignore                    # MODIFY: e2e.db, e2e/.seed.json, test-results/
  src/components.tsx            # MODIFY: data-testid na ContainerFormModal
  e2e/
    seed-types.ts               # CREATE: typy SeedData
    global-setup.ts             # CREATE: seed przez REST → .seed.json
    fixtures.ts                 # CREATE: test.extend (seeded, loginAs)
    pages/
      LoginPage.ts              # CREATE
      QueuePage.ts              # CREATE
      ContainerPage.ts          # CREATE
    scoping.spec.ts             # CREATE
    container-crud.spec.ts      # CREATE
    login.spec.ts               # ISTNIEJE — bez zmian
README.md                       # MODIFY: sekcja E2E
```

---

### Task 1: Konfiguracja Playwright + gitignore + przeglądarka

**Files:**
- Modify: `frontend/playwright.config.ts`
- Modify: `frontend/.gitignore` (utwórz jeśli brak)

**Interfaces:**
- Produces: config z `globalSetup: './e2e/global-setup.ts'`, artefaktami i `use.baseURL`. Kolejne taski zakładają, że `.seed.json`, `e2e.db`, `test-results/` są ignorowane przez git.

- [ ] **Step 1: Podmień `frontend/playwright.config.ts`**

```ts
import { defineConfig } from '@playwright/test'

// E2E lokalny (nie w blocking CI — patrz .github/workflows/e2e.yml, workflow_dispatch):
// odpala backend (uvicorn, SQLite dev) + frontend (vite dev) i klika w prawdziwej przeglądarce.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,   // wspólny backend/baza — testy po kolei, bez wyścigów o stan
  reporter: 'list',
  globalSetup: './e2e/global-setup.ts',
  outputDir: 'test-results',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: [
    {
      command: 'python -m uvicorn app.main:app --port 8000',
      cwd: '../backend',
      url: 'http://localhost:8000/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      env: { DATABASE_URL: 'sqlite:///./e2e.db' },
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
})
```

- [ ] **Step 2: Utwórz/rozszerz `frontend/.gitignore`**

Dopisz (jeśli plik istnieje — dołóż linie; jeśli nie — utwórz z tą treścią):

```
# E2E Playwright
/test-results/
/playwright-report/
/e2e/.seed.json
```

Dodatkowo w **`backend/.gitignore`** upewnij się, że jest linia `e2e.db` (baza E2E). Jeśli pliku nie ma, utwórz go z treścią:

```
e2e.db
```

- [ ] **Step 3: Zainstaluj przeglądarkę Playwright**

Run: `cd frontend && npx playwright install chromium`
Expected: pobranie Chromium bez błędu (lub „is already installed").

- [ ] **Step 4: Zweryfikuj, że config parsuje i widzi istniejące testy**

Run: `cd frontend && npx playwright test --list`
Expected: lista zawiera 3 testy z `login.spec.ts`, brak błędu ładowania configu.

- [ ] **Step 5: Commit**

```bash
git add frontend/playwright.config.ts frontend/.gitignore backend/.gitignore
git commit -m "test(e2e): config artefaktów Playwright + gitignore baz/wyników E2E"
```

---

### Task 2: Seed danych przez REST (global-setup)

**Files:**
- Create: `frontend/e2e/seed-types.ts`
- Create: `frontend/e2e/global-setup.ts`

**Interfaces:**
- Consumes: REST backendu (`/api/auth/login`, `/api/companies`, `/api/users`, `/api/containers`).
- Produces:
  - `SeedData` (seed-types.ts): `{ password: string; userA: {login:string; companyId:number}; userB: {login:string; companyId:number}; containerA: {no:string}; containerB: {id:number; no:string} }`.
  - Plik `frontend/e2e/.seed.json` z obiektem `SeedData`, czytany przez fixtures (Task 3).

- [ ] **Step 1: Utwórz `frontend/e2e/seed-types.ts`**

```ts
export interface SeededUser {
  login: string
  companyId: number
}

export interface SeedData {
  /** wspólne hasło wszystkich zasianych userów E2E */
  password: string
  userA: SeededUser
  userB: SeededUser
  containerA: { no: string }
  containerB: { id: number; no: string }
}
```

- [ ] **Step 2: Utwórz `frontend/e2e/global-setup.ts`**

```ts
import { request } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { SeedData } from './seed-types'

const API = 'http://localhost:8000'
const E2E_PASSWORD = 'E2ePass123!'

// Seed przez REST admina: bootstrap() sieje tylko admina, więc scoped userów i
// kontenery A/B tworzymy tu. Uruchamiane raz przed wszystkimi testami (globalSetup).
export default async function globalSetup() {
  // baza e2e.db jest świeża na starcie backendu tylko jeśli usunięta; przy
  // reuseExistingServer lokalnie może zostać po poprzednim biegu. Seed jest
  // idempotentny na loginach/numerach — 409 (konflikt) traktujemy jako „już jest".
  const ctx = await request.newContext({ baseURL: API })

  // 1. login admina — OAuth2PasswordRequestForm (x-www-form-urlencoded)
  const login = await ctx.post('/api/auth/login', {
    form: { username: 'admin', password: 'admin123' },
  })
  if (!login.ok()) throw new Error(`Seed: login admina nieudany (${login.status()})`)

  // 2. dwie różne firmy z domyślnego seedu
  const companiesRes = await ctx.get('/api/companies')
  const companies = (await companiesRes.json()) as Array<{ id: number; code: string }>
  if (companies.length < 2) throw new Error('Seed: potrzebne min. 2 firmy w bootstrapie')
  const companyA = companies[0]
  const companyB = companies[1]

  // 3. userzy logistics scoped do A i do B (idempotentnie)
  async function ensureUser(login: string, companyId: number) {
    const res = await ctx.post('/api/users', {
      data: {
        login, full_name: `E2E ${login}`, password: E2E_PASSWORD,
        send_invite: false, role: 'logistics', company_id: companyId,
        view_all_companies: false, is_active: true,
      },
    })
    if (!res.ok() && res.status() !== 409) {
      throw new Error(`Seed: user ${login} nieudany (${res.status()}): ${await res.text()}`)
    }
  }
  await ensureUser('e2e_a', companyA.id)
  await ensureUser('e2e_b', companyB.id)

  // 4. kontenery A/B (numery ISO 6346 poprawne)
  async function ensureContainer(no: string, companyId: number): Promise<number> {
    const res = await ctx.post('/api/containers', { data: { container_no: no, company_id: companyId } })
    if (res.ok()) return (await res.json()).id as number
    if (res.status() === 409) {
      // już istnieje — znajdź po numerze na liście admina (widzi wszystko)
      const list = await ctx.get('/api/containers')
      const found = ((await list.json()) as Array<{ id: number; container_no: string }>)
        .find(c => c.container_no === no)
      if (found) return found.id
    }
    throw new Error(`Seed: kontener ${no} nieudany (${res.status()}): ${await res.text()}`)
  }
  const idA = await ensureContainer('MSDU0806613', companyA.id)
  const idB = await ensureContainer('TCLU1234568', companyB.id)

  const seed: SeedData = {
    password: E2E_PASSWORD,
    userA: { login: 'e2e_a', companyId: companyA.id },
    userB: { login: 'e2e_b', companyId: companyB.id },
    containerA: { no: 'MSDU0806613' },
    containerB: { id: idB, no: 'TCLU1234568' },
  }
  writeFileSync(join(__dirname, '.seed.json'), JSON.stringify(seed, null, 2))
  await ctx.dispose()
  void idA
}
```

- [ ] **Step 3: Uruchom istniejący login.spec — globalSetup wykona seed**

Run: `cd frontend && npm run e2e -- login.spec.ts`
Expected: 3 testy login PASS; powstaje plik `frontend/e2e/.seed.json`.

- [ ] **Step 4: Zweryfikuj kształt `.seed.json`**

Run: `cd frontend && node -e "const s=require('./e2e/.seed.json'); if(!s.userA.login||!s.containerB.id) throw new Error('zły seed'); console.log('seed ok', s.userA.login, s.userB.login, s.containerB.no)"`
Expected: `seed ok e2e_a e2e_b TCLU1234568`

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/seed-types.ts frontend/e2e/global-setup.ts
git commit -m "test(e2e): global-setup — seed firm/userów/kontenerów przez REST"
```

---

### Task 3: Fixtures + Page Objects + test izolacji multi-company

**Files:**
- Create: `frontend/e2e/fixtures.ts`
- Create: `frontend/e2e/pages/LoginPage.ts`
- Create: `frontend/e2e/pages/QueuePage.ts`
- Create: `frontend/e2e/pages/ContainerPage.ts`
- Create: `frontend/e2e/scoping.spec.ts`

**Interfaces:**
- Consumes: `SeedData` z `.seed.json` (Task 2).
- Produces:
  - `test` (fixtures.ts) rozszerzony o `seeded: SeedData` i `loginAs: (login: string) => Promise<void>`.
  - `LoginPage` z metodą `login(user: string, pass: string): Promise<void>`.
  - `QueuePage` z `goto(): Promise<void>` i `hasContainer(no: string): Promise<boolean>`.
  - `ContainerPage` z `goto(id: number): Promise<void>`.

- [ ] **Step 1: Utwórz `frontend/e2e/pages/LoginPage.ts`**

```ts
import type { Page } from '@playwright/test'

// Logowanie przez modal z topnavu (selektory jak w login.spec.ts).
export class LoginPage {
  constructor(private page: Page) {}

  async login(user: string, pass: string): Promise<void> {
    await this.page.goto('/')
    await this.page.getByRole('navigation').getByRole('button', { name: 'Zaloguj się' }).click()
    await this.page.locator('#kl-login').fill(user)
    await this.page.locator('#kl-pass').fill(pass)
    await this.page.getByRole('button', { name: 'Zaloguj się' }).click()
    await this.page.getByText('Wyloguj').waitFor()
  }
}
```

- [ ] **Step 2: Utwórz `frontend/e2e/pages/QueuePage.ts`**

```ts
import type { Page } from '@playwright/test'

// Lista kolejki pod /kolejka; numery kontenerów renderowane jako unikalny tekst mono.
export class QueuePage {
  constructor(private page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto('/kolejka')
  }

  async hasContainer(no: string): Promise<boolean> {
    return this.page.getByText(no, { exact: true }).first().isVisible().catch(() => false)
  }
}
```

- [ ] **Step 3: Utwórz `frontend/e2e/pages/ContainerPage.ts`**

```ts
import type { Page } from '@playwright/test'

// Karta kontenera pod /kontenery/{id}. Edycja przez przycisk „Edytuj" (rola admin/logistics).
export class ContainerPage {
  constructor(private page: Page) {}

  async goto(id: number): Promise<void> {
    await this.page.goto(`/kontenery/${id}`)
  }

  async startEdit(): Promise<void> {
    await this.page.getByRole('button', { name: 'Edytuj' }).click()
    await this.page.getByTestId('container-form').waitFor()
  }

  async setContainerNo(no: string): Promise<void> {
    await this.page.getByTestId('container-no-input').fill(no)
  }

  async submit(): Promise<void> {
    await this.page.getByTestId('container-submit').click()
  }
}
```

- [ ] **Step 4: Utwórz `frontend/e2e/fixtures.ts`**

```ts
import { test as base } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { SeedData } from './seed-types'
import { LoginPage } from './pages/LoginPage'

const seed = JSON.parse(readFileSync(join(__dirname, '.seed.json'), 'utf-8')) as SeedData

export const test = base.extend<{ seeded: SeedData; loginAs: (login: string) => Promise<void> }>({
  seeded: async ({}, use) => { await use(seed) },
  loginAs: async ({ page }, use) => {
    await use(async (login: string) => {
      await new LoginPage(page).login(login, seed.password)
    })
  },
})

export { expect } from '@playwright/test'
```

- [ ] **Step 5: Napisz test izolacji `frontend/e2e/scoping.spec.ts`**

```ts
import { test, expect } from './fixtures'
import { QueuePage } from './pages/QueuePage'
import { ContainerPage } from './pages/ContainerPage'

test.describe('Izolacja multi-company', () => {
  test('user firmy A nie widzi kontenera firmy B na liście kolejki', async ({ page, loginAs, seeded }) => {
    await loginAs(seeded.userA.login)
    const queue = new QueuePage(page)
    await queue.goto()
    await expect(page.getByText(seeded.containerA.no, { exact: true }).first()).toBeVisible()
    await expect(page.getByText(seeded.containerB.no, { exact: true })).toHaveCount(0)
  })

  test('user firmy A nie ma dostępu do karty kontenera firmy B (403)', async ({ page, loginAs, seeded }) => {
    await loginAs(seeded.userA.login)
    const detail = new ContainerPage(page)
    await detail.goto(seeded.containerB.id)
    // karta B nigdy się nie renderuje — numer B nie pojawia się na stronie
    await expect(page.getByText(seeded.containerB.no, { exact: true })).toHaveCount(0)
  })
})
```

- [ ] **Step 6: Uruchom test izolacji**

Run: `cd frontend && npm run e2e -- scoping.spec.ts`
Expected: 2 testy PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/e2e/fixtures.ts frontend/e2e/pages frontend/e2e/scoping.spec.ts
git commit -m "test(e2e): fixtures + page objects + test izolacji multi-company"
```

---

### Task 4: data-testid na formularzu + test edycji i walidacji ISO 6346

**Files:**
- Modify: `frontend/src/components.tsx` (`ContainerFormModal`)
- Create: `frontend/e2e/container-crud.spec.ts`

**Interfaces:**
- Consumes: `seeded`, `loginAs` (Task 3); `ContainerPage` page object (Task 3).
- Produces: `data-testid` na formularzu kontenera: `container-form` (form), `container-no-input` (input numeru), `container-submit` (przycisk zapisu), `form-error` (`<p class="error">`).

- [ ] **Step 1: Dodaj `data-testid` w `ContainerFormModal` (`frontend/src/components.tsx`)**

W elemencie `<form onSubmit={submit}>` dodaj atrybut `data-testid="container-form"`:

```tsx
      <form onSubmit={submit} data-testid="container-form">
```

Na inpucie numeru kontenera (pole `container_no`) dodaj `data-testid="container-no-input"`:

```tsx
          <label>{t('containerNo')} *
            <input value={form.container_no} required data-testid="container-no-input"
                   onChange={e => set('container_no', e.target.value.toUpperCase())}
                   placeholder="MSDU0806613" />
          </label>
```

Na komunikacie błędu dodaj `data-testid="form-error"`:

```tsx
        {error && <p className="error" data-testid="form-error">{error}</p>}
```

Na przycisku zapisu dodaj `data-testid="container-submit"`:

```tsx
          <button className="btn" disabled={busy} data-testid="container-submit">{t('save')}</button>
```

- [ ] **Step 2: Zweryfikuj, że frontend dalej się typuje i buduje**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: brak błędów TS, build OK.

- [ ] **Step 3: Napisz test edycji + ISO 6346 `frontend/e2e/container-crud.spec.ts`**

```ts
import { test, expect } from './fixtures'
import { QueuePage } from './pages/QueuePage'
import { ContainerPage } from './pages/ContainerPage'

test.describe('Kontener — widoczność, edycja, ISO 6346', () => {
  test('kontener utworzony w seedzie jest widoczny na liście właściciela', async ({ page, loginAs, seeded }) => {
    await loginAs(seeded.userA.login)
    const queue = new QueuePage(page)
    await queue.goto()
    await expect(page.getByText(seeded.containerA.no, { exact: true }).first()).toBeVisible()
  })

  test('błędny numer ISO 6346 przy edycji jest blokowany komunikatem z backendu', async ({ page, loginAs, seeded }) => {
    await loginAs(seeded.userA.login)
    // wejdź na kartę własnego kontenera (id znajdujemy przez API listy po zalogowaniu)
    const list = await page.request.get('http://localhost:8000/api/containers')
    const mine = ((await list.json()) as Array<{ id: number; container_no: string }>)
      .find(c => c.container_no === seeded.containerA.no)
    expect(mine).toBeTruthy()

    const detail = new ContainerPage(page)
    await detail.goto(mine!.id)
    await detail.startEdit()
    await detail.setContainerNo('MSDU0806615')   // zła cyfra kontrolna
    await detail.submit()

    // backend zwraca 4xx z polskim komunikatem ISO 6346 → widoczny w form-error
    await expect(page.getByTestId('form-error')).toContainText('ISO 6346')
    // numer nie zmienił się na błędny w tytule/treści karty
    await expect(page.getByText('MSDU0806615', { exact: true })).toHaveCount(0)
  })
})
```

- [ ] **Step 4: Uruchom test CRUD/ISO**

Run: `cd frontend && npm run e2e -- container-crud.spec.ts`
Expected: 2 testy PASS.

- [ ] **Step 5: Pełny bieg E2E (regresja całości)**

Run: `cd frontend && npm run e2e`
Expected: wszystkie specи (login + scoping + container-crud) PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components.tsx frontend/e2e/container-crud.spec.ts
git commit -m "test(e2e): data-testid formularza + test edycji i walidacji ISO 6346"
```

---

### Task 5: Dokumentacja uruchamiania E2E

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nic. Produces: sekcja README opisująca E2E.

- [ ] **Step 1: Dodaj do `README.md` sekcję (w miejscu opisu testów; jeśli brak — przed sekcją deployu)**

```markdown
## Testy E2E (Playwright)

E2E odpala realny backend (uvicorn, SQLite `e2e.db`) i frontend (`vite dev`),
klika w przeglądarce. Seed danych (firmy, userzy per rola, kontenery) robi
`e2e/global-setup.ts` przez REST admina.

```bash
cd frontend
npx playwright install chromium   # raz
npm run e2e                        # headless (jak CI)
npm run e2e -- --headed            # z widoczną przeglądarką (debug widoku)
npm run e2e -- --debug             # inspektor krok po kroku
```

**Uwaga:** E2E serwuje frontend z `vite dev`, **nie** z commitowanego `dist/` —
ręczny rebuild `dist/` nie jest potrzebny do testów E2E (dotyczy tylko podglądu
produkcyjnego builda). Artefakty faili (screenshot/trace/wideo) lądują w
`frontend/test-results/`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(e2e): instrukcja uruchamiania testów Playwright"
```

---

## Self-Review

**Spec coverage:**
- Auth per rola → Task 3 (LoginPage + `loginAs`, użyte w scoping i crud). ✎ istniejący login.spec.ts pokrywa admina; loginAs pokrywa role scoped.
- Security multi-company → Task 3 (`scoping.spec.ts`: lista + brak dostępu do karty B).
- Add (API) + widoczność na liście → Task 2 (seed tworzy kontener) + Task 4 (asercja widoczności).
- Edycja + ISO 6346 negatywnie → Task 4.
- data-testid → Task 4. Seed przez API admina → Task 2. Artefakty/uruchamianie → Task 1 + Task 5.

**Placeholder scan:** brak TBD/TODO; każdy krok ma realny kod lub komendę z oczekiwanym wynikiem.

**Type consistency:** `SeedData` (userA/userB/containerA/containerB) spójne między seed-types.ts, global-setup.ts, fixtures.ts, oboma specami. Metody page objectów (`login`, `goto`, `startEdit`, `setContainerNo`, `submit`, `hasContainer`) użyte zgodnie z definicją. `data-testid` (`container-form`, `container-no-input`, `container-submit`, `form-error`) spójne między komponentem a testami.

## Ryzyka / uwagi wykonawcze

- **Selektor `Wyloguj`/`Zaloguj się`** pochodzi z działającego `login.spec.ts` — jeśli i18n zmieni teksty, LoginPage trzeba zaktualizować (świadomy dług: login jest przed montażem kontekstu języka, PL domyślny).
- **403 na karcie B**: asercja opiera się na tym, że numer B nie renderuje się (karta nie ładuje się bez dostępu). Jeśli ContainerPage renderuje numer z URL zanim padnie błąd — zmień asercję na widoczny `LoadError`.
- **Reuse bazy lokalnie**: przy `reuseExistingServer` `e2e.db` może przetrwać między biegami; seed jest idempotentny (409 = już jest). W CI (`CI=1`) serwery startują świeżo.
