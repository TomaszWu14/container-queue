// Audyt UI — stany: ładowanie, błąd API, pusty, modale/menu (kluczowe widoki, 1366 + telefon).
import { chromium } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const BASE = 'http://localhost:5180'
const LABEL = process.argv[2] || 'before'
const OUT = path.resolve('..', 'audit', 'raw', LABEL, 'states')
fs.mkdirSync(OUT, { recursive: true })
const KEY = ['/kolejka', '/pulpit', '/kalendarz', '/sledzenie', '/reklamacje', '/spedycja']
const VIEWS = { d1366: { viewport: { width: 1366, height: 768 } },
  phone: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 3 } }
const browser = await chromium.launch()
const log = []

async function ctxFor(user, pass, v) {
  const ctx = await browser.newContext({ ...v, locale: 'pl-PL', timezoneId: 'Europe/Warsaw' })
  await ctx.addInitScript(() => localStorage.setItem('onboarded', '1'))
  const r = await ctx.request.post(`${BASE}/api/auth/login`, { form: { username: user, password: pass } })
  if (!r.ok()) throw new Error('login ' + user)
  return ctx
}
const shot = async (page, name) => {
  await page.screenshot({ path: path.join(OUT, name + '.jpg'), type: 'jpeg', quality: 70 })
  log.push(name)
}
const safe = async (fn) => { try { await fn() } catch (e) { log.push('BŁĄD ' + String(e).slice(0, 120)) } }

for (const [vn, v] of Object.entries(VIEWS)) {
  if (process.env.ONLY_MENUS) { await menus(vn, v); continue }
  // 1) ładowanie: API wstrzymane 4 s, zrzut po 800 ms
  const cl = await ctxFor('admin', 'admin123', v)
  const pl = await cl.newPage()
  await pl.route('**/api/**', async r => {
    if (r.request().url().includes('/auth/')) return r.continue()
    await new Promise(res => setTimeout(res, 4000)); return r.continue()
  })
  for (const u of KEY) await safe(async () => {
    pl.goto(BASE + u).catch(() => {}); await pl.waitForTimeout(800)
    await shot(pl, `loading__${u.slice(1)}__${vn}`)
  })
  await cl.close()
  // 2) błąd: API (poza auth) → 500
  const ce = await ctxFor('admin', 'admin123', v)
  const pe = await ce.newPage()
  await pe.route('**/api/**', r => r.request().url().includes('/auth/')
    ? r.continue() : r.fulfill({ status: 500, body: '{"detail":"Internal Server Error"}', contentType: 'application/json' }))
  for (const u of KEY) await safe(async () => {
    await pe.goto(BASE + u, { waitUntil: 'networkidle', timeout: 20000 }).catch(() => {})
    await pe.waitForTimeout(500); await shot(pe, `error__${u.slice(1)}__${vn}`)
  })
  await ce.close()
  // 3) pusty: spółka bez danych
  const cp = await ctxFor('ux_empty', 'Audit-2026!', v)
  const pp = await cp.newPage()
  for (const u of KEY) await safe(async () => {
    await pp.goto(BASE + u, { waitUntil: 'networkidle', timeout: 20000 }).catch(() => {})
    await pp.waitForTimeout(500); await shot(pp, `empty__${u.slice(1)}__${vn}`)
  })
  await cp.close()
  await menus(vn, v)
}
async function menus(vn, v) {
  // 4) modale i menu na kolejce (logistyka)
  const cm = await ctxFor('ux_logistics', 'Audit-2026!', v)
  const pm = await cm.newPage()
  await pm.goto(BASE + '/kolejka', { waitUntil: 'networkidle' }).catch(() => {})
  await pm.waitForTimeout(600)
  await safe(async () => {
    await pm.getByRole('button', { name: /dodaj/i }).first().click({ timeout: 4000 })
    await pm.waitForTimeout(500); await shot(pm, `modal__dodaj-kontener__${vn}`)
    await pm.keyboard.press('Escape'); await pm.waitForTimeout(300)
  })
  await safe(async () => {
    await pm.locator('.kq-more-btn').first().click({ timeout: 4000 })
    await pm.waitForTimeout(400); await shot(pm, `menu__wiersz-kolejki__${vn}`)
    await pm.keyboard.press('Escape'); await pm.mouse.click(5, 300)
  })
  await safe(async () => {
    await pm.locator('.kq-more-menu').first().click({ timeout: 4000 })
    await pm.waitForTimeout(400); await shot(pm, `menu__kolejka-wiecej__${vn}`)
    await pm.keyboard.press('Escape'); await pm.mouse.click(5, 300)
  })
  await safe(async () => {
    await pm.locator('.tn-user').first().click({ timeout: 4000 })
    await pm.waitForTimeout(400); await shot(pm, `menu__uzytkownik__${vn}`)
    await pm.keyboard.press('Escape')
  })
  await cm.close()
}
fs.writeFileSync(path.join(OUT, process.env.ONLY_MENUS ? 'log-menus.json' : 'log.json'), JSON.stringify(log, null, 1))
await browser.close()
console.log(log.length, 'wpisów', log.filter(l => l.startsWith('BŁĄD')).length, 'błędów')
