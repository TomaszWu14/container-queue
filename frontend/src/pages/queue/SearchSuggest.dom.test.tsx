// @vitest-environment jsdom
// Strażnik wyszukiwarki z podpowiedziami (2026-09-24/25): start od 2 znaków z debounce
// i anulowaniem poprzedniego żądania, typ + pogrubiony fragment, ↑↓/Enter wybiera, Esc
// zamyka, aria-activedescendant, pusty wynik = komunikat, wklejka normalizowana i
// przycinana do 50 znaków z informacją „Skrócono…".
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../../api', () => ({ api: { get: apiGet } }))
vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))

import SearchSuggest, { type Suggestion } from './SearchSuggest'

const S: Suggestion = { type: 'po', label: '4500617421', container_id: 7, container_no: 'MSDU0806613',
  notify_date: '2026-10-14', warehouse: 'DLT', vessel: null, supplier_id: null }
const V: Suggestion = { ...S, type: 'vessel', label: 'EVER 1742 GIVEN', container_id: 8 }

function Harness({ onPick, initial = '' }: { onPick: (s: Suggestion) => void; initial?: string }) {
  const [v, setV] = useState(initial)
  return <SearchSuggest value={v} onChange={setV} onPick={onPick} placeholder="szukaj" completed={false} />
}

afterEach(() => { cleanup(); vi.useRealTimers(); apiGet.mockReset() })

const type = async (input: HTMLElement, value: string, ms = 260) => {
  fireEvent.change(input, { target: { value } })
  await act(async () => { await vi.advanceTimersByTimeAsync(ms) })
}

describe('SearchSuggest', () => {
  it('od 2 znaków, debounce, klawiatura wybiera, Esc zamyka, aria-activedescendant', async () => {
    vi.useFakeTimers()
    apiGet.mockResolvedValue([S, V])
    const onPick = vi.fn()
    render(<Harness onPick={onPick} />)
    const input = screen.getByRole('combobox')
    await type(input, '4')
    expect(apiGet).not.toHaveBeenCalled()
    await type(input, '1742')
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet.mock.calls[0][0]).toBe('/api/search/suggest?q=1742&completed=false')
    expect(screen.getByText('sugPo')).toBeTruthy()
    const opts = screen.getAllByRole('option')
    expect(opts[0].querySelector('b')!.textContent).toBe('1742')
    expect(opts[1].querySelector('b')!.textContent).toBe('1742')       // środek etykiety statku
    expect(opts[1].textContent).toContain('14.10.2026')
    expect(input.getAttribute('aria-activedescendant')).toBe(opts[0].id)
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(input.getAttribute('aria-activedescendant')).toBe(opts[1].id)
    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect(opts[0].getAttribute('aria-selected')).toBe('true')
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(input.getAttribute('aria-expanded')).toBe('false')
    await type(input, '17421')
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onPick).toHaveBeenCalledWith(V)
  })

  it('szybkie pisanie: jedno żądanie po debounce, poprzednie anulowane', async () => {
    vi.useFakeTimers()
    const signals: AbortSignal[] = []
    apiGet.mockImplementation((_p: string, signal: AbortSignal) => {
      signals.push(signal)
      return new Promise(() => {})   // wisi — tylko sprawdzamy anulowanie
    })
    render(<Harness onPick={() => {}} />)
    const input = screen.getByRole('combobox')
    await type(input, 'ms', 100)
    await type(input, 'msd', 100)
    expect(apiGet).not.toHaveBeenCalled()          // debounce: nic przed 250 ms ciszy
    await type(input, 'msdu', 260)
    await type(input, 'msdu8', 260)
    expect(apiGet).toHaveBeenCalledTimes(2)
    expect(signals[0].aborted).toBe(true)         // nowy znak anulował wiszące żądanie
    expect(signals[1].aborted).toBe(false)
  })

  it('wybór wpisujący etykietę do pola nie otwiera listy ponownie', async () => {
    vi.useFakeTimers()
    apiGet.mockResolvedValue([V])
    function PickSets() {
      const [v, setV] = useState('')
      return <SearchSuggest value={v} onChange={setV} onPick={s => setV(s.label)} placeholder="szukaj" />
    }
    render(<PickSets />)
    const input = screen.getByRole('combobox') as HTMLInputElement
    await type(input, 'ever')
    fireEvent.keyDown(input, { key: 'Enter' })
    await act(async () => { await vi.advanceTimersByTimeAsync(300) })
    expect(input.value).toBe(V.label)
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('brak wyników = komunikat z zapytaniem', async () => {
    vi.useFakeTimers()
    apiGet.mockResolvedValue([])
    render(<Harness onPick={() => {}} />)
    await type(screen.getByRole('combobox'), 'zzz')
    expect(screen.getByText('sugNone')).toBeTruthy()
  })

  it('wklejka: nowe linie → spacja, przycięcie do 50 znaków + informacja', () => {
    render(<Harness onPick={() => {}} />)
    const input = screen.getByRole('combobox') as HTMLInputElement
    expect(input.maxLength).toBe(50)
    fireEvent.paste(input, { clipboardData: { getData: () => ` MSDU0806613\r\n${'x'.repeat(60)}` } })
    expect(input.value).toHaveLength(50)
    expect(input.value.startsWith('MSDU0806613 x')).toBe(true)
    expect(screen.getByRole('status').textContent).toBe('searchTrimmed')
  })

  it('wklejka z \\n mieszcząca się w limicie — bez informacji, wstawiona w miejsce zaznaczenia', () => {
    render(<Harness onPick={() => {}} initial="AB-CD" />)
    const input = screen.getByRole('combobox') as HTMLInputElement
    input.setSelectionRange(2, 3)                  // zaznaczony „-"
    fireEvent.paste(input, { clipboardData: { getData: () => '\n1 \n 2\n' } })
    expect(input.value).toBe('AB1 2CD')
    expect(screen.queryByRole('status')).toBeNull()
  })
})
