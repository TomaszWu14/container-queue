// @vitest-environment jsdom
// C9 (audyt UI): brak magazynów z limitem → jeden komunikat zamiast siatki „0 /0” i KPI z zerami
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../i18n', async () => {
  const { createContext } = await import('react')
  return { useT: () => (k: string) => k, LangContext: createContext({ lang: 'pl' }), localeFor: () => 'pl-PL' }
})
const { dicts, role } = vi.hoisted(() => ({ dicts: { warehouses: [] as object[] }, role: { v: 'logistics' } }))
vi.mock('../../components', () => ({ useDicts: () => dicts }))
vi.mock('../../userContext', () => ({ useUser: () => ({ role: role.v }) }))
vi.mock('../../api', () => ({ api: { get: () => Promise.resolve([]) }, errorMessage: String }))

import CalendarPage from '../CalendarPage'

afterEach(() => { cleanup(); role.v = 'logistics' })
const setup = () => render(<MemoryRouter initialEntries={['/kalendarz?widok=miesiac&rok=2026&miesiac=09']}>
  <CalendarPage /></MemoryRouter>)

it('pojemność 0: komunikat z linkiem do magazynów, bez siatki i KPI', async () => {
  setup()
  expect(await screen.findByText('calNoCapacityTitle')).toBeTruthy()
  expect(screen.getByRole('link', { name: 'calNoCapacityLink' }).getAttribute('href')).toBe('/master-data/magazyny')
  expect(document.querySelector('.cal2-day')).toBeNull()
  expect(document.querySelector('.cal2-kpis')).toBeNull()
})

it('magazyn/spedytor: komunikat bez linku do ustawień', async () => {
  role.v = 'warehouse'
  setup()
  expect(await screen.findByText('calNoCapacityTitle')).toBeTruthy()
  expect(screen.queryByRole('link', { name: 'calNoCapacityLink' })).toBeNull()
})
