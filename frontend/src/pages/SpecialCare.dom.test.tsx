// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({
  api: { get: apiGet, post: vi.fn(), patch: vi.fn(), del: vi.fn(), upload: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('../App', () => ({ useUser: () => ({ role: 'admin' }) }))
vi.mock('../feedback', async (orig) => ({
  ...(await orig() as object), useToast: () => ({ showToast: vi.fn() }),
}))

afterEach(() => { cleanup(); apiGet.mockReset() })

const ORDERS = [
  {
    id: 1, company_id: 1, name: 'Zamówienie A', customer_name: 'Klient A',
    order_refs: 'REF-1', deadline: '2026-10-01', max_etd: '2026-09-15', buffer_days: 5,
    responsible_id: null, responsible_name: null, alert_on_delay: true, note: '',
    created_at: '', matched_count: 1, earliest_etd: null, latest_eta: '2026-10-05',
    departed: false, trigger_etd_missed: true, trigger_forecast_late: false, at_risk: true,
    matched: [{ id: 1, container_no: 'CONT1' }],
  },
  {
    id: 2, company_id: 1, name: 'Zamówienie B', customer_name: 'Klient B',
    order_refs: 'REF-2', deadline: '2026-11-01', max_etd: '2026-10-15', buffer_days: 5,
    responsible_id: null, responsible_name: null, alert_on_delay: true, note: '',
    created_at: '', matched_count: 0, earliest_etd: null, latest_eta: null,
    departed: false, trigger_etd_missed: false, trigger_forecast_late: false, at_risk: false,
    matched: [],
  },
]

describe('SpecialCarePage — lista ryzyka', () => {
  it('renderuje obie nazwy, badge ryzyka i filtr „tylko zagrożone"', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/customer-orders') return Promise.resolve(ORDERS)
      if (path === '/api/companies') return Promise.resolve([{ id: 1, name: 'Firma', code: 'F1', is_active: true }])
      // S10: lekka lista osób zamiast admin-only /api/users
      if (path === '/api/customer-orders/responsibles') return Promise.resolve([{ id: 5, name: 'Anna Nowak' }])
      return Promise.reject(new Error('unexpected ' + path))
    })
    const { default: SpecialCarePage } = await import('./SpecialCarePage')
    render(<SpecialCarePage />)

    expect(await screen.findByText('Zamówienie A')).toBeTruthy()
    expect(screen.getByText('Zamówienie B')).toBeTruthy()
    expect(screen.getByText('Nie wypłynął w terminie')).toBeTruthy()
    expect(screen.getByText('OK')).toBeTruthy()
    expect(await screen.findByRole('option', { name: 'Anna Nowak' })).toBeTruthy()

    const filter = screen.getByLabelText('Tylko zagrożone')
    fireEvent.click(filter)

    expect(screen.getByText('Zamówienie A')).toBeTruthy()
    expect(screen.queryByText('Zamówienie B')).toBeNull()
  })
})
