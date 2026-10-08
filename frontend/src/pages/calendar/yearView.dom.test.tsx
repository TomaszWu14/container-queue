// @vitest-environment jsdom
// Widok roczny kalendarza: przełączanie Rok/Miesiąc ↔ URL, ‹ › między latami,
// klik kafelka (miesiąc) i dnia (miesiąc + dzien), jeden agregat /api/calendar/year.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { heat, yearIndex } from './YearView'

vi.mock('../../i18n', async () => {
  const { createContext } = await import('react')
  return { useT: () => (k: string) => k, LangContext: createContext({ lang: 'pl' }), localeFor: () => 'pl-PL' }
})
vi.mock('../../components', () => ({ useDicts: () => ({ warehouses: [] }) }))
const apiGet = vi.fn((url: string) => Promise.resolve(url.startsWith('/api/calendar/year')
  ? { year: 2026, today: '2026-09-25', days: [
      { day: '2026-03-02', warehouse: 'DLT', count: 2 }, { day: '2026-03-02', warehouse: null, count: 1 },
      { day: '2026-03-03', warehouse: 'Acme', count: 6 }] }
  // miesiąc: po jednej awizacji 2026-03-02 i dziś (bez tego siatkę zastępuje komunikat C9)
  : [today(), '2026-03-02'].map(day => ({ day, is_free_day: false, containers: [
      { warehouse_name: 'X', customs_status: 'ODPRAWIONY', is_delayed: false, eta: null }] }))))
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
vi.mock('../../api', () => ({ api: { get: (u: string) => apiGet(u) }, errorMessage: String }))

import CalendarPage from '../CalendarPage'

afterEach(() => { cleanup(); apiGet.mockClear() })

function Loc() { const l = useLocation(); return <output data-testid="loc">{l.search}</output> }
const setup = (url: string) => render(
  <MemoryRouter initialEntries={[url]}><CalendarPage /><Loc /></MemoryRouter>)
const loc = () => screen.getByTestId('loc').textContent

describe('kalendarz — widok roczny', () => {
  it('agregat: podział na magazyny, liczby i skala intensywności', async () => {
    setup('/kalendarz?widok=rok&rok=2026')
    await screen.findByText('DLT')
    expect(apiGet).toHaveBeenCalledWith('/api/calendar/year?rok=2026')
    expect(apiGet.mock.calls.some(([u]) => u.startsWith('/api/queue'))).toBe(false)
    const march = document.querySelectorAll('.cal2-ym')[2]
    expect(march.querySelector('.cal2-ym-total b')!.textContent).toBe('9')
    expect(march.textContent).toContain('calNoWarehouse')
    expect(document.querySelectorAll('.cal2-ym')[8].getAttribute('aria-current')).toBe('date')
    expect(document.querySelector('.cal2-ym-day.today')!.getAttribute('title')).toContain('2026-09-25')
    expect(heat(6, 6)).toBe(4); expect(heat(3, 6)).toBe(2); expect(heat(0, 6)).toBe(0)
    expect(yearIndex({ year: 2026, today: '', days: [{ day: 'd', warehouse: 'Dlt', count: 2 }] }, 'ACME').size).toBe(0)
  })

  it('‹ › zmieniają rok w URL; klik kafelka → miesiąc; klik dnia → miesiąc + dzień', async () => {
    setup('/kalendarz?widok=rok&rok=2026')
    await screen.findByText('DLT')
    fireEvent.click(screen.getByLabelText('nextYear'))
    expect(loc()).toBe('?widok=rok&rok=2027')
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/calendar/year?rok=2027'))
    fireEvent.click(screen.getByLabelText('prevYear'))
    await screen.findByText('DLT')
    fireEvent.click(document.querySelectorAll('.cal2-ym-head')[2])
    expect(loc()).toBe('?widok=miesiac&rok=2026&miesiac=03')
    fireEvent.click(screen.getByText('calViewYear'))
    expect(loc()).toBe('?widok=rok&rok=2026')
    fireEvent.click(await screen.findByTitle(/^2026-03-02/))
    expect(loc()).toBe('?widok=miesiac&rok=2026&miesiac=03&dzien=2026-03-02')
    await waitFor(() => expect(document.querySelector('.cal2-day[aria-label^="2026-03-02"]')
      ?.getAttribute('aria-pressed')).toBe('true'))
  })

  it('bez parametrów: widok miesięczny bieżącego miesiąca (dane z /api/queue)', async () => {
    setup('/kalendarz')
    const now = new Date()
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith(expect.stringMatching(/^\/api\/queue\?/)))
    const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    expect(document.querySelector(`.cal2-day[aria-label^="${ym}-01"]`)).toBeTruthy()
    fireEvent.click(screen.getByText('calViewYear'))
    expect(loc()).toBe(`?widok=rok&rok=${now.getFullYear()}`)
  })
})
