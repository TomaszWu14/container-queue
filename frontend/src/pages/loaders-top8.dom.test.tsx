// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { OrderDetailPage } from './OrdersPage'
import CalendarPage from './CalendarPage'

// TOP 8 audytu — ciche loadery głównego contentu → LoadError + retry.
vi.mock('../i18n', async () => {
  const { createContext } = await import('react')
  return {
    useT: () => (key: string) => ({ retry: 'Spróbuj ponownie' } as Record<string, string>)[key] ?? key,
    LangContext: createContext({ lang: 'pl' }),
    localeFor: () => 'pl-PL',
  }
})
vi.mock('../components', () => ({
  useDicts: () => ({ warehouses: [] }),
  CustomsBadge: () => null,
  StatusBadge: () => null,
  Kpi: () => null,
}))

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({ api: { get: apiGet }, errorMessage: (e: unknown) => String(e) }))

afterEach(() => { cleanup(); apiGet.mockReset() })

describe('TOP 8 — loadery bez cichego faila', () => {
  it('OrderDetailPage: błąd API pokazuje LoadError z retry zamiast cichego navigate', async () => {
    apiGet.mockImplementationOnce(() => Promise.reject(new Error('boom')))
    apiGet.mockImplementationOnce(() => Promise.resolve({
      id: 1, number: 'PO-1', company_name: null, supplier_name: null, notes: null,
      container_count: 0, containers: [],
      progress: { total: 0, delivered: 0, percent: 0, derived_status: 'PUSTE' },
    }))
    render(
      <MemoryRouter initialEntries={['/zamowienia/1']}>
        <Routes><Route path="/zamowienia/:id" element={<OrderDetailPage />} /></Routes>
      </MemoryRouter>,
    )
    const retryBtn = await screen.findByText('Spróbuj ponownie')
    fireEvent.click(retryBtn)
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2))
    // trasa backendu to /api/orders/{id} (/zamowienia to tylko ścieżka SPA → wcześniej 404)
    expect(apiGet).toHaveBeenCalledWith('/api/orders/1')
  })

  it('CalendarPage: skeleton przy ładowaniu, LoadError z retry po błędzie', async () => {
    apiGet.mockImplementationOnce(() => Promise.reject(new Error('boom')))
    apiGet.mockImplementationOnce(() => Promise.resolve([]))
    render(<MemoryRouter><CalendarPage /></MemoryRouter>)

    expect(document.querySelector('.skeleton')).toBeTruthy()
    const retryBtn = await screen.findByText('Spróbuj ponownie')
    fireEvent.click(retryBtn)
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2))
  })
})
