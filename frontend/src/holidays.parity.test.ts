import { describe, expect, it } from 'vitest'
import { holidayName, holidayNames, isHoliday, type Country } from './holidays'
import snapshot from './holidays.snapshot.json'

// Lustro backend/app/holidays.py: ten sam snapshot sprawdza
// backend/tests/test_holidays_snapshot.py — rozjazd którejkolwiek strony = czerwony test.
describe('holidays.ts == backend/app/holidays.py', () => {
  for (const [country, years] of Object.entries(snapshot) as [Country, Record<string, string[]>][]) {
    it(`${country}: te same dni co backend`, () => {
      for (const [year, days] of Object.entries(years)) {
        expect([...holidayNames(Number(year), country).keys()].sort()).toEqual(days)
      }
    })
  }
})

describe('kraj kalendarza', () => {
  it('PT ma swoje święta, nie polskie', () => {
    expect(isHoliday('2026-04-25', 'PT')).toBe(true)
    expect(isHoliday('2026-04-03', 'PT')).toBe(true)      // Wielki Piątek
    expect(isHoliday('2026-11-11', 'PT')).toBe(false)     // Niepodległość PL
    expect(isHoliday('2026-11-11')).toBe(true)            // domyślnie PL
    expect(holidayName('2026-06-10', 'PT')).toBe('Dia de Portugal')
  })
})
