// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import PurchaseOrdersPanel from './PurchaseOrdersPanel'

// S10 (audyt UI): panel zamówień ETD tylko dla ról z dostępem do /api/purchase-orders —
// spedytor (decyzja: NIE), magazyn i agencja nie wołają API zamiast łapać 403.
vi.mock('../i18n', async (orig) => ({
  ...await orig<typeof import('../i18n')>(), useT: () => (k: string) => k,
}))
const { role } = vi.hoisted(() => ({ role: { v: 'logistics' } }))
vi.mock('../App', () => ({ useUser: () => ({ role: role.v }) }))
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({ api: { get: apiGet } }))

afterEach(() => { cleanup(); apiGet.mockReset(); role.v = 'logistics' })

it('logistyka widzi zamówienia ETD', async () => {
  apiGet.mockResolvedValue([{ id: 1, order_no: '4500000001', supplier: 'X', products: '', cbm: null,
    container_type: '', etd: null, ready_date: '', port_of_departure: '', forwarder: '' }])
  render(<PurchaseOrdersPanel companyCode="ACME" />)
  expect(await screen.findByText('4500000001')).toBeTruthy()
})

it.each(['forwarder', 'warehouse', 'customs'])('%s: brak zapytania i brak panelu', r => {
  role.v = r
  const { container } = render(<PurchaseOrdersPanel companyCode="ACME" />)
  expect(apiGet).not.toHaveBeenCalled()
  expect(container.innerHTML).toBe('')
})
