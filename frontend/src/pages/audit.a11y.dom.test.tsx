// @vitest-environment jsdom
// Strażnik audytu a11y: dzień w kalendarzu (widok miesiąca) wybierany z klawiatury.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../i18n', async () => {
  const { createContext } = await import('react')
  return {
    useT: () => (key: string) => key,
    LangContext: createContext({ lang: 'pl' }),
    localeFor: () => 'pl-PL',
  }
})
vi.mock('../components', () => ({ useDicts: () => ({ warehouses: [] }), Kpi: () => null }))
// jedna awizacja w bieżącym miesiącu — pusty miesiąc bez limitów pokazuje komunikat C9 zamiast siatki
const d0 = new Date()
const day0 = `${d0.getFullYear()}-${String(d0.getMonth() + 1).padStart(2, '0')}-01`
vi.mock('../api', () => ({
  api: { get: () => Promise.resolve([{ day: day0, is_free_day: false, containers: [
    { warehouse_name: 'X', customs_status: 'ODPRAWIONY', is_delayed: false, eta: null }] }]) },
  errorMessage: (e: unknown) => String(e),
}))

import CalendarPage from './CalendarPage'

afterEach(cleanup)

describe('CalendarPage — komórka dnia jako przycisk', () => {
  it('Enter i Spacja wybierają dzień; komórka jest w kolejności tabulacji', async () => {
    render(<MemoryRouter><CalendarPage /></MemoryRouter>)
    fireEvent.click(await screen.findByText('calViewMonth'))
    const now = new Date()
    const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    const pick = (d: string) =>
      document.querySelector<HTMLElement>(`.cal2-day[aria-label^="${ym}-${d}"]`)!
    const day = now.getDate() === 15 ? '16' : '15'
    expect(pick(day).getAttribute('role')).toBe('button')
    expect(pick(day).tabIndex).toBe(0)
    expect(pick(day).getAttribute('aria-pressed')).toBe('false')
    fireEvent.keyDown(pick(day), { key: 'Enter' })
    expect(pick(day).getAttribute('aria-pressed')).toBe('true')
    fireEvent.keyDown(pick('01'), { key: ' ' })
    expect(pick('01').getAttribute('aria-pressed')).toBe('true')
    expect(pick(day).getAttribute('aria-pressed')).toBe('false')
  })
})
