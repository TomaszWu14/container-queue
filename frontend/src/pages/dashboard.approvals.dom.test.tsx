// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DashboardPage from './DashboardPage'

// #47: karta faktur do akceptacji na Wieży — tylko admin, tylko status DO_AKCEPTACJI.
vi.mock('../i18n', async (orig) => ({
  ...await orig<typeof import('../i18n')>(), useT: () => (k: string) => k,
}))
vi.mock('../DocumentsW5', () => ({ DocsGapsCard: () => null }))
const { role } = vi.hoisted(() => ({ role: { v: 'admin' } }))
vi.mock('../App', () => ({ useUser: () => ({ role: role.v }) }))
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({ api: { get: apiGet }, errorMessage: String }))

const DASH = { today: 0, tomorrow: 0, in_transit: 0, at_port: 0, customs_in_progress: 0, delayed: 0,
  today_list: [], demurrage_list: [], delayed_list: [], action_feed: [] }
const FI = [
  { id: 1, bl_number: 'BL-WAIT', invoice_number: 'F1', amount: 100, currency: 'USD', status: 'DO_AKCEPTACJI' },
  { id: 2, bl_number: 'BL-DONE', invoice_number: 'F2', amount: 50, currency: 'USD', status: 'ZAAKCEPTOWANA' },
]
function setup() {
  apiGet.mockImplementation((url: string) =>
    url.includes('/api/stats/dashboard') ? Promise.resolve(DASH)
      : url.includes('/api/freight-invoices') ? Promise.resolve(FI)
        : Promise.resolve({ created: [], status: [], eta: [] }))
  render(<MemoryRouter><DashboardPage /></MemoryRouter>)
}
afterEach(() => { cleanup(); apiGet.mockReset(); role.v = 'admin' })

describe('FreightApprovalsCard', () => {
  it('admin widzi tylko faktury DO_AKCEPTACJI', async () => {
    setup()
    expect(await screen.findByText(/BL-WAIT/)).toBeTruthy()
    expect(screen.queryByText(/BL-DONE/)).toBeNull()
  })
  it('nie-admin nie pobiera faktur', async () => {
    role.v = 'logistics'
    setup()
    await screen.findAllByText(/.+/, { selector: 'div' })
    expect(apiGet.mock.calls.some(([u]) => String(u).includes('freight-invoices'))).toBe(false)
  })
})
