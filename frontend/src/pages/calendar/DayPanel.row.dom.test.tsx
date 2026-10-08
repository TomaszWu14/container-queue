// @vitest-environment jsdom
// A23 (audyt UI): wiersz kontenera w panelu dnia — status jak w kolejce, odprawa z kontekstem
import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DayPanel from './DayPanel'
import type { QueueDay } from '../../types'
import { dayStat } from './calModel'

vi.mock('../../i18n', async () => {
  const { createContext } = await import('react')
  const pl: Record<string, string> = { customs: 'Odprawa', cs_BRAK: 'Brak', st_W_PORCIE: '4 · Port docelowy' }
  return { useT: () => (k: string) => pl[k] ?? k, LangContext: createContext({ lang: 'pl' }), localeFor: () => 'pl-PL' }
})

it('status-pill kontenera i „Odprawa: brak”, bez „—” przy braku godziny', () => {
  const info = { day: '2026-09-14', is_free_day: false, containers: [{ id: 1, container_no: 'MSDU0806613',
    warehouse_name: 'DLT', status: 'W_PORCIE', customs_status: 'BRAK', is_delayed: false, slot_time: null,
    eta: null }] } as unknown as QueueDay
  const s = dayStat(info, [{ key: 'DLT', limit: 6 }])
  render(<MemoryRouter><DayPanel iso="2026-09-14" info={info} s={s} holiday={null} /></MemoryRouter>)
  const row = screen.getByText('MSDU0806613').closest('.cal2-p-row')!
  expect(row.querySelector('.badge.st-W_PORCIE')?.textContent).toBe('4 · Port docelowy')
  expect(row.querySelector('.cal2-cs')?.textContent?.trim()).toBe('Odprawa: brak')
  expect(row.querySelector('.cal2-p-time')?.textContent).toBe('')
})
