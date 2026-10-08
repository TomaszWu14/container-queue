// @vitest-environment jsdom
// audyt UI PR 7d: na telefonie siatka miesiąca jest listą — karta dnia niesie skrót dnia tygodnia
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (k: string) => k }))

import DayCard from './DayCard'
import type { DayStat } from './calModel'

afterEach(cleanup)

const s: DayStat = { total: 0, cap: 7, free: 7, over: 0, late: 0, customsOpen: 0, revision: 0,
  vessels: 0, toPort: 0, byWh: [], closed: false }

describe('DayCard — dzień tygodnia', () => {
  it.each([['2026-09-28', 'mo'], ['2026-09-04', 'fr'], ['2026-09-27', 'su']])('%s → %s', (iso, key) => {
    const { container } = render(<DayCard iso={iso} s={s} holiday={null} selected={false} today={false} onSelect={() => {}} />)
    expect(container.querySelector('.cal2-dow')?.textContent).toBe(key)
  })
})
