// @vitest-environment jsdom
// Wywołania-DLT: analityka (sort/filtr wg zapasu w dniach) + kreator aut
// (licznik 33/132, prefill podpowiedzi).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({
  api: { get: apiGet, post: vi.fn(), upload: vi.fn() },
  downloadFile: vi.fn(), errorMessage: (e: unknown) => String(e),
}))
vi.mock('../App', () => ({ useUser: () => ({ role: 'logistics' }) }))
vi.mock('../feedback', async (orig) => ({
  ...(await orig() as object), useToast: () => ({ showToast: vi.fn() }),
}))

afterEach(() => { cleanup(); apiGet.mockReset() })

const row = (produkt: string, extra: Record<string, unknown> = {}) => ({
  produkt, stan_mag_pal: 10, stan_dlt_pal: 20, dostawy_pal: 0,
  zlec_niepotw_pal: 0, zlec_potw_pal: 0, wywolane_pal: 0, projekcja_mag_pal: 10,
  dni_zapasu: 5, pilne: false, sugestia_pal: 4, stan_mag_szt: 1000,
  stan_dlt_szt: 2000, zuzycie_szt_dzien: 100, cel_dni: 14, hu: [], ...extra,
})

function mockAnalysis(items: unknown[]) {
  apiGet.mockImplementation((path: string) => {
    if (path.startsWith('/api/pallet-calls/analysis'))
      return Promise.resolve({ items, total: items.length, fetched_at: null,
                               discrepancies: [], features: { hu: true, daily_usage: true } })
    if (path === '/api/pallet-calls') return Promise.resolve([])
    if (path === '/api/paz') return Promise.resolve([])
    return Promise.reject(new Error('x'))
  })
}

describe('sortByDaysAsc / truckLoads (logika kreatora)', () => {
  it('sortuje po zapasie w dniach rosnąco, null na końcu', async () => {
    const { sortByDaysAsc } = await import('./PalletCallsPage')
    const out = sortByDaysAsc([
      row('B', { dni_zapasu: 9 }), row('C', { dni_zapasu: null }),
      row('A', { dni_zapasu: 1 }),
    ] as never)
    expect(out.map(r => r.produkt)).toEqual(['A', 'B', 'C'])
  })

  it('liczy miejsca per auto (ceil ułamka) i flaguje przekroczenia 33/132', async () => {
    const { truckLoads } = await import('./PalletCallsPage')
    const ok = truckLoads([
      { produkt: 'A', ilosc_pal: 33, pallets: 32.2, truck_no: 1 },
      { produkt: 'B', ilosc_pal: 10, truck_no: 2 },
    ])
    expect(ok.perTruck).toEqual({ 1: 33, 2: 10 })
    expect(ok.total).toBe(43)
    expect(ok.overTruck).toEqual([])
    expect(ok.overTotal).toBe(false)

    const over = truckLoads([{ produkt: 'A', ilosc_pal: 34, truck_no: 1 }])
    expect(over.overTruck).toEqual([1])
    expect(truckLoads([{ produkt: 'A', ilosc_pal: 133 }]).overTotal).toBe(true)
  })
})

describe('tabela analityki', () => {
  it('renderuje wiersze posortowane po dniach zapasu i kolumnę celu dni', async () => {
    mockAnalysis([row('WOLNY', { dni_zapasu: 30 }), row('KRYTYCZNY', { dni_zapasu: 1, cel_dni: 28 })])
    const { default: PalletCallsPage } = await import('./PalletCallsPage')
    render(<PalletCallsPage />)
    await screen.findByText('KRYTYCZNY')
    const cells = screen.getAllByRole('row').map(r => r.textContent ?? '')
    const iKryt = cells.findIndex(c => c.includes('KRYTYCZNY'))
    const iWolny = cells.findIndex(c => c.includes('WOLNY'))
    expect(iKryt).toBeGreaterThan(0)
    expect(iKryt).toBeLessThan(iWolny)          // najkrótszy zapas u góry
    expect(cells[iKryt]).toContain('28')        // cel dni per materiał
  })

  it('filtr „poniżej celu" dokłada below_target=true do zapytania', async () => {
    mockAnalysis([row('A')])
    const { default: PalletCallsPage } = await import('./PalletCallsPage')
    render(<PalletCallsPage />)
    await screen.findByText('A')
    fireEvent.click(screen.getByLabelText(/poniżej celu/i))
    // zapytanie idzie po debounce 250 ms
    await waitFor(() => expect(apiGet.mock.calls
      .some(([p]) => String(p).includes('below_target=true'))).toBe(true),
      { timeout: 2000 })
  })
})

describe('kreator wywołania', () => {
  it('prefill z podpowiedzi + przydział auta pokazuje licznik zajętości', async () => {
    mockAnalysis([row('A', { sugestia_pal: 4 }), row('B', { sugestia_pal: 7 })])
    const { default: PalletCallsPage } = await import('./PalletCallsPage')
    render(<PalletCallsPage />)
    await screen.findByText('A')
    fireEvent.click(screen.getByText(/Dodaj podpowiedzi do wywołania/i))
    // qty wypełnione podpowiedziami -> przycisk pokazuje (2)
    expect(screen.getByText(/Utwórz wywołanie \(2\)/)).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Auto A'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Auto B'), { target: { value: '1' } })
    const loads = screen.getByTestId('truck-loads')
    expect(loads.textContent).toContain('Auto 1: 11/33')
    expect(loads.textContent).toContain('∑ 11/132')
  })
})
