import { describe, expect, it } from 'vitest'
import { workingDaysInYear, workingHoursInYear } from './holidays'

// Wartości zgodne z oficjalnym kalendarzem dni roboczych PL.
describe('workingDaysInYear', () => {
  it('liczy dni robocze 2026 i 2027 (bez weekendów i świąt PL)', () => {
    expect(workingDaysInYear(2026)).toBe(253)
    expect(workingDaysInYear(2027)).toBe(253)
  })

  it('godziny robocze = dni × 8h domyślnie', () => {
    expect(workingHoursInYear(2026)).toBe(253 * 8)
    expect(workingHoursInYear(2027, 8)).toBe(2024)
  })

  it('przyjmuje inną długość dnia pracy', () => {
    expect(workingHoursInYear(2026, 7.5)).toBe(253 * 7.5)
  })
})
