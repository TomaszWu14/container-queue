import { expect, test, type Page } from '@playwright/test'

// Strażnik regresji wizualnej po audycie UI (Etap 3): kluczowe widoki w jasnym i ciemnym motywie,
// desktop 1366 i telefon 390. Dane z seedu e2e; zegar zamrożony, ruchome elementy zamaskowane.
// daleka przyszłość: serwerowe flagi „opóźniony/demurrage” liczone od prawdziwej daty się nie zmienią
const FIXED_NOW = new Date('2030-04-08T09:00:00+02:00')
const DESKTOP = { width: 1366, height: 768 }
const PHONE = { width: 390, height: 844 }

// kolejka z danymi (seed e2e ma 2 kontenery bez dat): 3 kontenery Acme w zamrożonym tygodniu,
// idempotentnie — widok kolejki i karty na telefonie mają co pokazać
test.beforeAll(async ({ request }) => {
  await request.post('/api/auth/login', { form: { username: 'admin', password: 'admin123' } })
  const companies = await (await request.get('/api/companies')).json() as Array<{ id: number; code: string }>
  const acme = companies.find(c => c.code.toUpperCase().startsWith('ZAR')) ?? companies[0]
  const wh = (await (await request.get('/api/warehouses')).json() as Array<{ id: number }>)[0]
  const rows: Array<[string, string]> = [['MSKU2722693', '2030-04-09'], ['HLXU2733056', '2030-04-10'], ['CMAU2726825', '2030-04-11']]
  // API przyjmuje powtórzony numer kontenera — idempotencja po stronie testu (beforeAll odpala się
  // przy każdym restarcie workera)
  const have = new Set((await (await request.get('/api/containers')).json() as Array<{ container_no: string }>)
    .map(c => c.container_no))
  for (const [no, day] of rows) {
    if (have.has(no)) continue
    const r = await request.post('/api/containers', { data: { container_no: no, company_id: acme.id,
      notify_date: day, warehouse_id: wh?.id ?? null } })
    expect(r.ok()).toBeTruthy()
  }
})

async function open(page: Page, url: string, theme: 'light' | 'dark' = 'light') {
  await page.clock.setFixedTime(FIXED_NOW)
  await page.addInitScript(t => {
    localStorage.setItem('onboarded', '1')
    localStorage.setItem('theme', t)
  }, theme)
  const r = await page.request.post('/api/auth/login', { form: { username: 'admin', password: 'admin123' } })
  expect(r.ok()).toBeTruthy()
  await page.goto(url)
  await page.waitForLoadState('networkidle')
  // czcionki @fontsource ładują się asynchronicznie — zrzut przed nimi = losowe różnice glifów
  await page.evaluate(() => document.fonts.ready)
}

// licznik powiadomień zależy od stanu bazy e2e — maskujemy dzwonek (zegary i „ostatnie odświeżenie”
// są deterministyczne dzięki zamrożonemu zegarowi)
// select.week-pick: natywny <select> renderuje tekst niedeterministycznie (±90 px między przebiegami)
const masks = (page: Page) => [page.getByRole('button', { name: 'Powiadomienia' }), page.locator('.tn-status'),
  page.locator('select.week-pick')]

test.describe('desktop 1366', () => {
  test.use({ viewport: DESKTOP })

  test('logowanie', async ({ page }) => {
    await page.clock.setFixedTime(FIXED_NOW)
    await page.goto('/')
    await expect(page).toHaveScreenshot('logowanie.png')
  })

  for (const theme of ['light', 'dark'] as const) {
    test(`kolejka ${theme}`, async ({ page }) => {
      await open(page, '/kolejka', theme)
      await expect(page).toHaveScreenshot(`kolejka-${theme}.png`, { mask: masks(page) })
    })
  }

  test('modal „Dodaj kontener” + potwierdzenie porzucenia', async ({ page }) => {
    await open(page, '/kolejka')
    await page.locator('.kq-add').click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page).toHaveScreenshot('modal-dodaj.png', { mask: masks(page) })
    await page.locator('.modal textarea').first().fill('zmiana')
    await page.keyboard.press('Escape')
    await expect(page.locator('.confirm-dialog')).toBeVisible()
    await expect(page).toHaveScreenshot('potwierdzenie.png', { mask: masks(page) })
  })

  test('stan pusty kolejki', async ({ page }) => {
    await page.route('**/api/containers?*', r => r.fulfill({ json: [] }))
    await open(page, '/kolejka')
    await expect(page.locator('.empty-state')).toBeVisible()
    await expect(page).toHaveScreenshot('kolejka-pusta.png', { mask: masks(page) })
  })

  test('stan błędu kolejki', async ({ page }) => {
    await page.route('**/api/containers?*', r => r.fulfill({ status: 500, body: 'Internal Server Error' }))
    await open(page, '/kolejka')
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page).toHaveScreenshot('kolejka-blad.png', { mask: masks(page) })
  })
})

test.describe('telefon 390', () => {
  test.use({ viewport: PHONE, isMobile: true, hasTouch: true })

  for (const theme of ['light', 'dark'] as const) {
    test(`kolejka — karty ${theme}`, async ({ page }) => {
      await open(page, '/kolejka', theme)
      await expect(page).toHaveScreenshot(`tel-kolejka-${theme}.png`, { mask: masks(page) })
    })
  }

  test('menu nawigacji (hamburger)', async ({ page }) => {
    await open(page, '/pulpit')
    await page.getByRole('button', { name: 'Otwórz menu' }).click()
    await expect(page).toHaveScreenshot('tel-menu.png', { mask: masks(page) })
  })

  test('kalendarz — lista dni', async ({ page }) => {
    await open(page, '/kalendarz')
    await expect(page).toHaveScreenshot('tel-kalendarz.png', { mask: masks(page) })
  })

  test('brak przewijania strony w poziomie', async ({ page }) => {
    for (const url of ['/kolejka', '/pulpit', '/kalendarz', '/master-data', '/administracja/uzytkownicy']) {
      await open(page, url)
      const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      expect(over, url).toBeLessThanOrEqual(1)
    }
  })
})
