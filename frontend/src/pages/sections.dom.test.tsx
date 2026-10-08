// @vitest-environment jsdom
// Administracja / Master data: płaskie adresy sekcji, stare ?tab=… → nowy URL,
// 403 per sekcja i brak przycisku dla roli bez dostępu, grupy w menu bocznym.
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { SECTIONS, legacyTarget } from './sections'

let role = 'admin'
const user = () => ({ id: 1, login: 'u', role, full_name: 'U',
  must_change_password: false, view_all_companies: role === 'admin' })
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
apiGet.mockImplementation((path: string) =>
  Promise.resolve(path.includes('/auth/me') ? user() : []))

vi.mock('../api', () => ({
  api: { get: apiGet, post: vi.fn(), patch: vi.fn(), del: vi.fn() },
  logoutRequest: () => Promise.resolve(),
  ApiError: class extends Error {},
  errorMessage: (e: unknown) => String(e),
  downloadCsv: vi.fn(), toCsv: vi.fn(),
}))
vi.mock('./DashboardPage', () => ({ default: () => <div>DASHBOARD</div> }))

afterEach(() => { cleanup(); apiGet.mockClear() })
// strony tras są leniwe (PERF-006) — pierwszy dynamiczny import w teście to zimna transformacja
// modułu; rozgrzewamy go raz, żeby limity czasu testów mierzyły nawigację, nie kompilację
beforeAll(async () => { await Promise.all([import('./MasterDataPage'), import('./AdminPage')]) }, 60_000)

import App from '../App'

function Where() {
  const { pathname, search } = useLocation()
  return <output data-testid="where">{pathname + search}</output>
}
function mount(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><App /><Where /></MemoryRouter>)
}
const where = () => screen.getByTestId('where').textContent
const nav = () => document.querySelector('.sec-nav')
// strona startowa obszaru: nawigacją są kafle (B31 — bez zdublowanego menu bocznego)
const tiles = () => document.querySelectorAll('.sec-tile')
const tileHrefs = () => Array.from(tiles()).map(a => a.getAttribute('href'))
const fetched = (prefix: string) => apiGet.mock.calls.some(c => String(c[0]).startsWith(prefix))

describe('sekcje — adresy i przekierowania', () => {
  it('/master-data/porty otwiera porty i pobiera tylko ich dane', async () => {
    role = 'admin'
    mount('/master-data/porty')
    await waitFor(() => expect(document.querySelector('.sec-h')?.textContent).toBe('Porty'),
      { timeout: 5000 })
    // nagłówek sekcji renderuje się przed wysłaniem zapytania — na obciążonym runnerze CI
    // sprawdzenie „od razu” było wyścigiem (flaky, 2026-09-27)
    await waitFor(() => expect(fetched('/api/ports')).toBe(true))
    expect(fetched('/api/users')).toBe(false)
    expect(fetched('/api/customers')).toBe(false)
    expect(document.querySelector('.sec-link.active')?.getAttribute('href')).toBe('/master-data/porty')
  })

  it.each([
    ['/administracja?tab=ports', '/master-data/porty'],
    ['/admin?tab=poImport', '/master-data/import-po'],
    ['/administracja?zakladka=porty', '/master-data/porty'],
    ['/administracja#users', '/administracja/uzytkownicy'],
    ['/administracja/porty', '/master-data/porty'],
    ['/master-data?tab=units', '/master-data/jednostki-materialow'],
  ])('stary adres %s → %s', async (from, to) => {
    role = 'admin'
    mount(from)
    await waitFor(() => expect(where()).toBe(to), { timeout: 5000 })
  })

  it('menu Administracji i Master data ma grupy', async () => {
    role = 'admin'
    mount('/administracja')
    await waitFor(() => expect(tiles().length).toBeGreaterThan(0), { timeout: 5000 })
    expect(nav()).toBeNull()
    const groups = () => Array.from(document.querySelectorAll('.sec-tiles-group h2'))
      .map(g => g.textContent)
    expect(groups()).toEqual(['Organizacja', 'System'])
    expect(tileHrefs()).toContain('/administracja/log-logowan')
    expect(tileHrefs()).not.toContain('/administracja/porty')
    cleanup()
    mount('/master-data')
    await waitFor(() => expect(tiles().length).toBeGreaterThan(0), { timeout: 5000 })
    expect(nav()).toBeNull()
    expect(groups()).toEqual(['Kartoteki', 'Słowniki', 'Importy', 'Kontrola danych'])
    expect(tiles().length).toBe(SECTIONS.filter(s => s.area === 'md').length)
    // w sekcji menu boczne z tymi samymi grupami jest
    cleanup()
    mount('/master-data/porty')
    await waitFor(() => expect(nav()).not.toBeNull(), { timeout: 5000 })
    expect(Array.from(document.querySelectorAll('.sec-group')).map(g => g.getAttribute('aria-label')))
      .toEqual(['Kartoteki', 'Słowniki', 'Importy', 'Kontrola danych'])
  })
})

describe('sekcje — uprawnienia', () => {
  it('logistyka: sekcja dawniej tylko adminowa → 403, bez przycisku w menu', async () => {
    role = 'logistics'
    mount('/master-data/klienci')
    await waitFor(() => expect(screen.getByText('403 — brak dostępu')).toBeTruthy(),
      { timeout: 5000 })
    expect(fetched('/api/customers')).toBe(false)
    cleanup()
    mount('/master-data')
    await waitFor(() => expect(tiles().length).toBeGreaterThan(0), { timeout: 5000 })
    expect(tileHrefs()).toContain('/master-data/dostawcy')
    for (const s of SECTIONS.filter(x => x.area === 'md' && !x.roles.includes('logistics'))) {
      expect(tileHrefs()).not.toContain(`/master-data/${s.slug}`)
    }
  })

  it('logistyka: Administracja → 403', async () => {
    role = 'logistics'
    mount('/administracja/uzytkownicy')
    await waitFor(() => expect(screen.getByText('403 — brak dostępu')).toBeTruthy(),
      { timeout: 5000 })
  })
})

describe('sections.ts', () => {
  it('sekcje z dawnej Administracji zostają tylko dla admina', () => {
    const fromAdmin = ['users', 'companies', 'customers', 'import', 'poImport', 'marmImport',
      'cportImport', 'dltImport', 'materials', 'forwarders', 'customsAgencies',
      'docTemplates', 'carriers', 'problems', 'checklist', 'notifRules', 'settings',
      'system', 'authLog']
    for (const key of fromAdmin) {
      expect(SECTIONS.find(s => s.legacy.includes(key))?.roles, key).toEqual(['admin'])
    }
  })

  it('slugi unikalne, bez polskich znaków; legacy jednoznaczne', () => {
    const slugs = SECTIONS.map(s => s.slug)
    expect(new Set(slugs).size).toBe(slugs.length)
    for (const s of slugs) expect(s).toMatch(/^[a-z0-9-]+$/)
    const legacy = SECTIONS.flatMap(s => s.legacy)
    expect(new Set(legacy).size).toBe(legacy.length)
    expect(legacyTarget('', '')).toBeNull()
    expect(legacyTarget('?tab=nieznana', '')).toBeNull()
  })
})
