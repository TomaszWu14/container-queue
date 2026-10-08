// @vitest-environment jsdom
// Master data → Zamówienia SAP: wolna odpowiedź starszego wyszukiwania nie nadpisuje nowszej,
// błąd API to komunikat (nie pusta tabela), obcięta lista mówi „pokazano X z Y”.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../i18n', async (orig) => ({
  ...await orig<typeof import('../../i18n')>(), useT: () => (k: string) => k,
}))
vi.mock('../../App', () => ({ useUser: () => ({ role: 'admin' }) }))
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../../api', () => ({ api: { get: apiGet, del: vi.fn() }, errorMessage: (e: Error) => e.message }))
const { totals } = vi.hoisted(() => ({ totals: new WeakMap<object, number>() }))
vi.mock('../../listTotal', () => ({ totalOf: (d: object) => totals.get(d) ?? null }))

import { SapOrdersTab } from './ImportedTabs'

afterEach(() => { cleanup(); apiGet.mockReset() })

const row = (order_no: string) => ({ id: order_no.length, order_no, supplier: 'S', etd: null,
  ready_date: '', transport_mode: '', purchase_decision: '', port_of_departure: '',
  amount: null, container_id: null, company_id: 1, created_at: '2026-10-01' })

const mount = () => render(<MemoryRouter><SapOrdersTab companies={[]} /></MemoryRouter>)

describe('SapOrdersTab', () => {
  it('regresja: spóźniona odpowiedź starszego filtra nie nadpisuje nowszej', async () => {
    const pending: Record<string, (v: unknown) => void> = {}
    apiGet.mockImplementation((url: string) => new Promise(res => {
      pending[new URLSearchParams(url.split('?')[1]).get('q') ?? ''] = res
    }))
    mount()
    await waitFor(() => expect(pending['']).toBeDefined(), { timeout: 2000 })
    fireEvent.change(screen.getByPlaceholderText('mdSearch'), { target: { value: 'NOWY' } })
    await waitFor(() => expect(pending['NOWY']).toBeDefined(), { timeout: 2000 })
    await act(async () => { pending['NOWY']([row('PO-NOWY')]) })
    await act(async () => { pending['']([row('PO-STARY')]) })   // starsza odpowiedź dociera później
    expect(screen.getByText('PO-NOWY')).toBeTruthy()
    expect(screen.queryByText('PO-STARY')).toBeNull()
  })

  it('błąd API → komunikat zamiast cichej pustej tabeli', async () => {
    apiGet.mockRejectedValue(new Error('Serwer nie odpowiedział'))
    mount()
    expect(await screen.findByText('Serwer nie odpowiedział', undefined, { timeout: 2000 })).toBeTruthy()
  })

  it('lista obcięta limitem → informacja „pokazano X z Y”', async () => {
    const data = [row('PO-1')]
    totals.set(data, 1500)
    apiGet.mockResolvedValue(data)
    mount()
    expect(await screen.findByRole('status', undefined, { timeout: 2000 })).toBeTruthy()
    expect(apiGet.mock.calls[0][0]).toContain('limit=')
  })
})
