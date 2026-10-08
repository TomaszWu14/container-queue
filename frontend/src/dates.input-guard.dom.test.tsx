// @vitest-environment jsdom
// Regresja: w polu daty zmiany awizacji wpisanie pierwszej cyfry roku („2”) dawało w Chrome
// wartość 0002-11-09 i od razu otwierało „Potwierdź przeniesienie” na 09.11.0002.
// Strażnik z dates.ts (instalowany w main.tsx) przepuszcza tylko pełny rok 2000–2099,
// a rok 1–2-cyfrowy uzupełnia do 20xx przy opuszczeniu pola / Enter.
import { useEffect, useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

vi.mock('./api', () => ({ api: { post: vi.fn() }, errorMessage: String }))
vi.mock('./i18n', async importOriginal => ({
  ...await importOriginal<typeof import('./i18n')>(), useT: () => (key: string) => key,
}))
vi.mock('./feedback', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

import { expandShortYear, installDateInputGuard, isOutOfRangeDate } from './dates'
import TileMenus, { useTileMenus } from './pages/queue/TileMenus'
import type { Container } from './types'

let uninstall = () => {}
beforeEach(() => { uninstall = installDateInputGuard() })
afterEach(() => { uninstall(); cleanup() })

const C = { id: 7, container_no: 'TXGU9929807', is_special: false, notify_date: '2026-09-28' } as Container

function DateMenuHarness({ onMove }: { onMove: (v: { ids: number[]; day: string }) => void }) {
  const m = useTileMenus(() => {})
  useEffect(() => { m.setDateMenu({ c: C, x: 10, y: 10 }) }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  return <TileMenus m={m} warehouseOptions={[]} canEdit setPendingMove={onMove}
                    watched={new Set()} toggleWatch={() => {}}
                    watchPrompt={null} confirmWatch={() => {}} cancelWatch={() => {}}
                    onDetails={() => {}} onStatus={null} statusLabel="Status" />
}

describe('helpery roku', () => {
  it('rok spoza 2000–2099 to nie data; pusta wartość przechodzi', () => {
    expect(['0002-11-09', '0020-11-09', '0202-11-09', '1999-01-01', '2100-01-01'].every(isOutOfRangeDate)).toBe(true)
    expect(isOutOfRangeDate('2026-11-09')).toBe(false)
    expect(isOutOfRangeDate('')).toBe(false)
  })
  it('rok 1–2-cyfrowy → 20xx, reszta bez zmian', () => {
    expect(expandShortYear('0026-11-09')).toBe('2026-11-09')
    expect(expandShortYear('0002-11-09')).toBe('2002-11-09')
    expect(expandShortYear('0202-11-09')).toBe('0202-11-09')
    expect(expandShortYear('2026-11-09')).toBe('2026-11-09')
  })
})

describe('zmiana daty awizacji z menu kafelka', () => {
  it('pierwsza cyfra roku („2” → 0002) nie otwiera potwierdzenia; pełny rok — tak', () => {
    const onMove = vi.fn()
    render(<DateMenuHarness onMove={onMove} />)
    const input = screen.getByLabelText('pickNewDate')
    for (const partial of ['0002-11-09', '0020-11-09', '0202-11-09']) {
      fireEvent.input(input, { target: { value: partial } })
      fireEvent.change(input, { target: { value: partial } })
    }
    expect(onMove).not.toHaveBeenCalled()
    fireEvent.change(input, { target: { value: '2026-11-09' } })
    expect(onMove).toHaveBeenCalledTimes(1)
    expect(onMove.mock.calls[0][0]).toMatchObject({ ids: [7], day: '2026-11-09' })
  })

  it('„26” → 2026 po opuszczeniu pola', () => {
    const onMove = vi.fn()
    render(<DateMenuHarness onMove={onMove} />)
    const input = screen.getByLabelText('pickNewDate')
    fireEvent.change(input, { target: { value: '0026-11-09' } })
    expect(onMove).not.toHaveBeenCalled()
    fireEvent.focusOut(input)
    expect(onMove).toHaveBeenCalledTimes(1)
    expect(onMove.mock.calls[0][0]).toMatchObject({ day: '2026-11-09' })
  })
})

describe('kontrolowane pole formularza', () => {
  function Form() {
    const [v, setV] = useState('2026-09-28')
    return <><input type="date" aria-label="d" value={v} onChange={e => setV(e.target.value)} /><output>{v}</output></>
  }
  it('stan nie łapie 0026; Enter uzupełnia do 2026', () => {
    render(<Form />)
    const input = screen.getByLabelText('d')
    fireEvent.change(input, { target: { value: '0026-11-09' } })
    expect(screen.getByRole('status').textContent).toBe('2026-09-28')
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByRole('status').textContent).toBe('2026-11-09')
  })
})
