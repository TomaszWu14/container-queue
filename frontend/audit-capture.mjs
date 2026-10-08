// Audyt UI: zrzuty każdego widoku × rola × wariant + pomiary automatyczne → audit/raw/*.json
// Uruchom: node audit-capture.mjs [etykieta]   (backend :8010 + vite :5180, seed ux_seed.py)
import { chromium } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import fs from 'node:fs'
import path from 'node:path'

const BASE = 'http://localhost:5180'
const LABEL = process.argv[2] || 'before'
const OUT = path.resolve('..', 'audit', 'raw', LABEL)
fs.mkdirSync(path.join(OUT, 'shots'), { recursive: true })

const USERS = {
  admin: ['admin', 'admin123'], logistics: ['ux_logistics', 'Audit-2026!'],
  warehouse: ['ux_warehouse', 'Audit-2026!'], forwarder: ['ux_forwarder', 'Audit-2026!'],
  customs: ['ux_customs', 'Audit-2026!'], purchasing: ['ux_purchasing', 'Audit-2026!'],
}
// widoczność tras per rola = tests/ui-permissions.yaml (skrót)
const ALL = ['admin', 'logistics', 'warehouse', 'forwarder', 'customs', 'purchasing']
const ROUTES = {
  '/pulpit': ['admin', 'logistics', 'forwarder'],
  '/kolejka': ALL,
  '/kolejka/archiwum': ['admin', 'logistics', 'forwarder'],
  '/profil': ALL, '/wiedza': ALL,
  '/kontenery/{id}': ALL,
  '/brama': ['admin', 'logistics', 'warehouse'],
  '/awizacje/propozycje': ['admin', 'logistics'], '/zlecenia-spedycyjne': ['admin', 'logistics'],
  '/specjalna-troska': ['admin', 'logistics'], '/wywolania-dlt': ['admin', 'logistics'],
  '/analityka': ['admin', 'logistics'], '/dziennik-zmian': ['admin', 'logistics'],
  '/master-data': ['admin', 'logistics'],
  '/koszyk': ['admin', 'logistics', 'purchasing'],
  '/kalendarz': ['admin', 'logistics', 'warehouse', 'forwarder'],
  '/sledzenie': ['admin', 'logistics', 'warehouse', 'forwarder'],
  '/reklamacje': ['admin', 'logistics', 'warehouse', 'forwarder'],
  '/zamowienia': ['admin', 'logistics', 'forwarder', 'purchasing'],
  '/spedycja': ['admin', 'logistics', 'forwarder', 'purchasing'],
  '/wyceny': ['admin', 'logistics', 'forwarder'],
  '/odprawa': ['admin', 'logistics'],
  '/administracja': ['admin'], '/administracja/uzytkownicy': ['admin'],
}
const VARIANTS = {
  d1920: { viewport: { width: 1920, height: 1080 } },
  d1366: { viewport: { width: 1366, height: 768 } },
  tablet: { viewport: { width: 820, height: 1180 }, hasTouch: true },
  phone: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 3 },
  zoom125: { viewport: { width: 1536, height: 864 }, deviceScaleFactor: 1.25 },
  dark: { viewport: { width: 1920, height: 1080 }, dark: true },
}
const ONLY_ROLE = process.env.ROLE
// ograniczenie pamięci/czasu: 1366/tablet/125% tylko dla kluczowych widoków
const KEY_VIEWS = ['/kolejka', '/pulpit', '/kalendarz', '/kontenery/{id}', '/sledzenie', '/spedycja']
const CORE_VARIANTS = ['d1920', 'phone', 'dark']

// pomiary w stronie — jedna funkcja, wynik do JSON
const MEASURE = ([touch, full]) => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el)
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' }
  const sel = (el) => el.id ? `#${el.id}` : el.tagName.toLowerCase() +
    (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '')
  const out = { overflowX: document.documentElement.scrollWidth - window.innerWidth,
    fractionalFont: {}, weights: {}, smallTargets: [], dates: [], emoji: [] }
  if (!full) { out.cls = (window.__cls || 0); return out }
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el)) continue
    const s = getComputedStyle(el)
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())
    if (own) {
      const fs = parseFloat(s.fontSize)
      if (Math.abs(fs - Math.round(fs)) > 0.05) out.fractionalFont[s.fontSize] = (out.fractionalFont[s.fontSize] || 0) + 1
      const fam = s.fontFamily.split(',')[0].replace(/["']/g, '')
      out.weights[`${fam} ${s.fontWeight}`] = (out.weights[`${fam} ${s.fontWeight}`] || 0) + 1
      const t = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ')
      const m = t.match(/\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\/\d{1,2}\/\d{2,4}\b|\b\d{1,2}\.\d{1,2}\.\d{2}\b(?!\d)/)
      if (m && out.dates.length < 15) out.dates.push(`${m[0]} @ ${sel(el)}`)
      const e = t.match(/\p{Extended_Pictographic}/u)
      if (e && out.emoji.length < 15) out.emoji.push(`${e[0]} @ ${sel(el)}`)
    }
    if (touch && el.matches('a,button,input,select,textarea,[role=button],[tabindex]:not([tabindex="-1"])')) {
      const r = el.getBoundingClientRect()
      if ((r.width < 44 || r.height < 44) && out.smallTargets.length < 40)
        out.smallTargets.push(`${Math.round(r.width)}×${Math.round(r.height)} ${sel(el)} „${(el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 25)}”`)
    }
  }
  out.cls = (window.__cls || 0)
  return out
}

async function login(ctx, role) {
  const [u, p] = USERS[role]
  const r = await ctx.request.post(`${BASE}/api/auth/login`, { form: { username: u, password: p } })
  if (!r.ok()) throw new Error(`login ${role}: ${r.status()}`)
}

const browser = await chromium.launch()
const results = []
const firstContainerId = {}
for (const role of Object.keys(USERS)) {
  if (ONLY_ROLE && role !== ONLY_ROLE) continue
  for (const [vname, v] of Object.entries(VARIANTS)) {
    const ctx = await browser.newContext({ ...v, dark: undefined, locale: 'pl-PL', timezoneId: 'Europe/Warsaw' })
    await ctx.addInitScript((dark) => {
      localStorage.setItem('onboarded', '1')
      if (dark) localStorage.setItem('theme', 'dark')
      window.__cls = 0
      new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value })
        .observe({ type: 'layout-shift', buffered: true })
    }, !!v.dark)
    await login(ctx, role)
    if (!firstContainerId[role]) {
      const r = await ctx.request.get(`${BASE}/api/containers?limit=1`)
      const j = r.ok() ? await r.json() : null
      const arr = Array.isArray(j) ? j : (j?.items || [])
      firstContainerId[role] = arr[0]?.id
    }
    const page = await ctx.newPage()
    const consoleErr = []; const failed = []
    page.on('console', m => { if (m.type() === 'error') consoleErr.push(m.text().slice(0, 160)) })
    page.on('response', r => { if (r.status() >= 400 && r.url().includes('/api/')) failed.push(`${r.status()} ${r.url().replace(BASE, '')}`) })
    for (const [route, roles] of Object.entries(ROUTES)) {
      if (!roles.includes(role)) continue
      if (!CORE_VARIANTS.includes(vname) && !KEY_VIEWS.includes(route)) continue
      if (route.includes('{id}') && !firstContainerId[role]) continue
      const url = route.replace('{id}', firstContainerId[role])
      consoleErr.length = 0; failed.length = 0
      const t0 = Date.now()
      try {
        await page.goto(BASE + url, { waitUntil: 'networkidle', timeout: 30000 })
      } catch { /* zapisz co jest */ }
      await page.waitForTimeout(600)
      const loadMs = Date.now() - t0
      const slug = `${role}__${url.replace(/[/{}]/g, '_').replace(/^_/, '') || 'root'}__${vname}`
      const file = `shots/${slug}.jpg`
      await page.screenshot({ path: path.join(OUT, file), type: 'jpeg', quality: 70 })
      const m = await page.evaluate(MEASURE, [!!v.hasTouch, vname === 'd1920' || vname === 'phone' || vname === 'dark'])
      let axe = null
      if (vname === 'd1920' || (vname === 'dark' && role === 'admin')) {
        try {
          const a = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
          axe = a.violations.map(x => ({ id: x.id, impact: x.impact, n: x.nodes.length,
            help: x.help, targets: x.nodes.slice(0, 3).map(n => n.target.join(' ')) }))
        } catch (e) { axe = [{ id: 'axe-error', help: String(e).slice(0, 100) }] }
      }
      results.push({ role, route, url, variant: vname, file, loadMs, finalUrl: page.url().replace(BASE, ''),
        consoleErr: [...consoleErr], failed: [...new Set(failed)], ...m, axe })
      process.stdout.write('.')
    }
    await ctx.close()
  }
}
fs.writeFileSync(path.join(OUT, `results-${ONLY_ROLE || 'all'}.json`), JSON.stringify(results, null, 1))
await browser.close()
console.log(`\n${results.length} zrzutów → ${OUT}`)
