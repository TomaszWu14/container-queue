import { describe, expect, it } from 'vitest'
import { formatDate, formatDateRange, formatDayLong } from './dates'

// Konwencja UI: daty zawsze dd.mm.rrrr; zakresy pełne, skrót tylko w obrębie roku.
describe('formatDate — szacowana', () => {
  it('~ przed datą', () => expect(formatDate('2026-09-24', true)).toBe('~24.09.2026'))
  it('null z approx → —', () => expect(formatDate(null, true)).toBe('—'))
})

describe('formatDateRange', () => {
  it('pełny zakres domyślnie', () =>
    expect(formatDateRange('2026-09-21', '2026-09-27')).toBe('21.09.2026–27.09.2026'))
  it('skrót w tym samym roku', () =>
    expect(formatDateRange('2026-09-21', '2026-09-27', true)).toBe('21.09–27.09.2026'))
  it('przełom roku zawsze pełny, nawet ze skrótem', () =>
    expect(formatDateRange('2026-12-28', '2027-01-03', true)).toBe('28.12.2026–03.01.2027'))
  it('ten sam dzień → jedna data', () =>
    expect(formatDateRange('2026-09-25', '2026-09-25T10:00:00', true)).toBe('25.09.2026'))
  it('brak końca → sama data; oba puste → —', () => {
    expect(formatDateRange('2026-09-21', null)).toBe('21.09.2026')
    expect(formatDateRange(null, undefined)).toBe('—')
  })
})

describe('formatDayLong', () => {
  it('„25 września 2026 – piątek"', () =>
    expect(formatDayLong('2026-09-25', 'pl-PL')).toBe('25 września 2026, piątek'))
})
