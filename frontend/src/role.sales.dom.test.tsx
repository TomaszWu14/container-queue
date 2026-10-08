// @vitest-environment jsdom
// Rola „sprzedaż” (2026-09-27): biała lista widoków + Specjalna troska tylko do podglądu,
// bez zapytań do API zamkniętych dla roli (spółki, lista osób).
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { canAccess, homeFor, type ViewKey } from './routing'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('./api', () => ({ api: { get: apiGet }, errorMessage: String }))
vi.mock('./userContext', () => ({ useUser: () => ({ role: 'sales' }) }))
afterEach(() => { cleanup(); apiGet.mockReset() })

it('biała lista: kolejka, karta, kalendarz, śledzenie — nic więcej', () => {
  const all: ViewKey[] = ['dashboard', 'kolejka', 'kolejka-arch', 'kontener', 'kalendarz', 'zamowienia',
    'spedycja', 'odprawa', 'wyceny', 'sledzenie', 'reklamacje', 'administracja', 'awizo']
  expect(all.filter(k => canAccess('sales', k))).toEqual(['kolejka', 'kontener', 'kalendarz', 'sledzenie'])
  expect(homeFor('sales')).toBe('/kolejka')
})

it('Specjalna troska: podgląd bez formularza i edycji, bez zapytań o spółki i osoby', async () => {
  apiGet.mockImplementation((url: string) => Promise.resolve(url === '/api/customer-orders' ? [{
    id: 1, company_id: 1, name: 'Zamówienie A', customer_name: 'Klient', order_refs: '', deadline: null,
    max_etd: null, buffer_days: 5, responsible_id: null, responsible_name: 'Anna', alert_on_delay: true,
    note: '', matched_count: 0, earliest_etd: null, latest_eta: null, departed: false,
    trigger_etd_missed: false, trigger_forecast_late: false, at_risk: false, matched: [] }] : []))
  const { default: SpecialCarePage } = await import('./pages/SpecialCarePage')
  render(<SpecialCarePage />)
  expect(await screen.findByText('Zamówienie A')).toBeTruthy()
  expect(screen.getByText(/Podgląd — zamówienia dodaje i edytuje logistyka/)).toBeTruthy()
  expect(document.querySelector('form')).toBeNull()
  expect(screen.queryByRole('button', { name: /edytuj|usuń/i })).toBeNull()
  expect(apiGet.mock.calls.map(c => c[0])).toEqual(['/api/customer-orders'])
})
