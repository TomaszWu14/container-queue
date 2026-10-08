import { describe, expect, it } from 'vitest'
import { formatDate, formatDateTime, formatNum, parseServerTs, relTime } from './dates'

// Runda 2 audytu — konwencja suity: daty dd.mm.rrrr, liczby z przecinkiem.
describe('formatDate', () => {
  it('ISO date → dd.mm.rrrr', () => expect(formatDate('2026-07-08')).toBe('08.07.2026'))
  it('ISO datetime → dd.mm.rrrr (obcina czas)', () =>
    expect(formatDate('2026-07-08T12:34:56')).toBe('08.07.2026'))
  it('puste → —', () => { expect(formatDate(null)).toBe('—'); expect(formatDate('')).toBe('—') })
})

describe('formatDateTime', () => {
  // oczekiwanie liczone tym samym zegarem lokalnym co implementacja — test
  // przechodzi w każdej strefie; sedno regresji: naiwny UTC ≡ wariant z „Z"
  const localOf = (isoZ: string) => {
    const d = new Date(isoZ)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`
  }
  it('naiwny UTC → czas lokalny (identycznie jak z Z)', () => {
    expect(formatDateTime('2026-07-08T12:34:56')).toBe(localOf('2026-07-08T12:34:56Z'))
    expect(formatDateTime('2026-07-08T12:34:56Z')).toBe(localOf('2026-07-08T12:34:56Z'))
  })
  it('sama data → dd.mm.rrrr', () => expect(formatDateTime('2026-07-08')).toBe('08.07.2026'))
  it('puste → —', () => expect(formatDateTime(null)).toBe('—'))
})

// Strefa czasu: backend zwraca naiwny UTC bez „Z" — parseServerTs musi traktować to
// jako UTC, inaczej relTime/próg-stale liczą z offsetem lokalnym (bug: fałszywe „X temu").
describe('parseServerTs', () => {
  it('naiwny UTC bez Z → traktowany jako UTC', () =>
    expect(parseServerTs('2026-09-06T12:00:00').getTime())
      .toBe(Date.UTC(2026, 8, 6, 12, 0, 0)))
  it('z Z → bez zmian', () =>
    expect(parseServerTs('2026-09-06T12:00:00Z').getTime())
      .toBe(Date.UTC(2026, 8, 6, 12, 0, 0)))
  it('z offsetem → uszanowany', () =>
    expect(parseServerTs('2026-09-06T14:00:00+02:00').getTime())
      .toBe(Date.UTC(2026, 8, 6, 12, 0, 0)))
})

describe('relTime — odporne na naiwny UTC', () => {
  const now = Date.UTC(2026, 8, 6, 12, 5, 0)  // 5 min po znaczniku
  it('naiwny UTC sprzed 5 min → „5 min temu" (nie przesunięte o strefę)', () =>
    expect(relTime('2026-09-06T12:00:00', 'pl', now)).toBe('5 min temu'))
})

describe('formatNum', () => {
  it('przecinek dziesiętny', () => expect(formatNum(5, 1)).toBe('5,0'))
  it('string też działa', () => expect(formatNum('12.5')).toBe('12,5'))
  it('null/NaN → —', () => { expect(formatNum(null)).toBe('—'); expect(formatNum('abc')).toBe('—') })
})
