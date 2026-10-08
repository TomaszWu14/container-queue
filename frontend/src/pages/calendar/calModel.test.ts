// Strażnik wyliczeń kalendarza awizacji (2026-09-24): obłożenie per magazyn, wolne sloty,
// ponad limit, opóźnienia, odprawy otwarte, statki z ETA, filtr magazynu, sumy miesiąca.
import { describe, expect, it } from 'vitest'
import { dayStat, monthWeeks, tone, totals } from './calModel'
import type { Container, QueueDay } from '../../types'

const c = (warehouse_name: string, extra: Partial<Container> = {}) =>
  ({ warehouse_name, customs_status: 'ZLECONA', is_delayed: false, ...extra }) as Container
const WHS = [{ key: 'ACME', limit: 7 }, { key: 'DLT', limit: 7 }]
const day = (containers: Container[], is_free_day = false) =>
  ({ day: '2026-10-23', containers, is_free_day, limit: null, used: 0, over_limit: false }) as QueueDay

describe('calModel', () => {
  it('dzień: sloty per magazyn, wolne, ponad limit, opóźnienia, odprawy, statki', () => {
    const dlt = Array.from({ length: 8 }, () => c('DLT'))
    const s = dayStat(day([c('ACME', { is_delayed: true }), c('ACME', { customs_status: 'ODPRAWIONY' }),
      c('ACME', { customs_status: 'REWIZJA' }), ...dlt]), WHS,
      [c('ACME', { vessel: 'EVER' }), c('DLT', { vessel: 'EVER' }), c('DLT', { vessel: 'MSC' })])
    expect(s.byWh).toEqual([{ key: 'ACME', limit: 7, n: 3 }, { key: 'DLT', limit: 7, n: 8 }])
    expect([s.total, s.cap, s.free, s.over, s.late]).toEqual([11, 14, 4, 1, 1])
    expect([s.customsOpen, s.revision, s.vessels, s.toPort]).toEqual([10, 1, 2, 3])
    expect(tone(s.total, s.cap)).toBe('high')
    expect(tone(0, 14)).toBe('none')   // pusty dzień bez tinty
  })

  it('filtr magazynu i sumy (dni zamknięte poza pojemnością)', () => {
    const s = dayStat(day([c('ACME'), c('DLT')]), WHS, [], 'DLT')
    expect([s.total, s.cap, s.byWh.length]).toEqual([1, 7, 1])
    const tot = totals([s, dayStat(day([], true), WHS)])
    expect([tot.bookings, tot.cap, tot.workdays]).toEqual([1, 7, 1])
  })

  it('siatka miesiąca od poniedziałku (paź 2026 zaczyna się w czwartek)', () => {
    const w = monthWeeks(2026, 9)
    expect(w[0].slice(0, 4)).toEqual([null, null, null, '2026-10-01'])
    expect(w.flat().filter(Boolean)).toHaveLength(31)
  })
})

// strażnik: nagłówki kalendarza przyklejone (clip zamiast hidden — hidden zabija sticky)
import { readFileSync } from 'node:fs'
describe('kalendarz — przyklejone nagłówki', () => {
  it('pasek miesiąca i dni tygodnia są sticky', () => {
    const css = readFileSync(new URL('../../styles/10-calendar-awizacji.css', import.meta.url), 'utf-8')
    expect(css).toMatch(/\.cal2-month > \.cal2-bar \{ position: sticky/)
    expect(css).toMatch(/\.cal2-grid > \.cal2-wd \{ position: sticky/)
    expect(css).not.toMatch(/\.cal2-month \{[^}]*overflow: hidden/)
  })
})
