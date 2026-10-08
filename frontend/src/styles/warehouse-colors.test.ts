// Strażnik palety magazynów (2026-09-24): tokeny --wh-* są jedynym źródłem kolorów
// wierszy DLT/ACME — reguły wierszy i akcenty chipów mają z nich czytać, nie z hexów.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { tokens } from './tokenMap'

const css = (f: string) => readFileSync(new URL(`./${f}`, import.meta.url), 'utf-8')

describe('kolory magazynów', () => {
  it('tokeny mają wartości ze specyfikacji (tła 2026-09-24; ramki z design systemu ≥ 3:1 do tła)', () => {
    const t = tokens('light')
    for (const [name, hex] of [['--wh-dlt', '#f4a1b8'], ['--wh-dlt-bg', '#f9d9e3'], ['--wh-dlt-border', '#c0567a'],
      ['--wh-acme', '#98fb98'], ['--wh-acme-bg', '#d2f7d2'], ['--wh-acme-border', '#2e8b2e']]) {
      expect(t[name], name).toBe(hex)
    }
  })

  it('wiersze i chipy DLT/ACME korzystają z tokenów', () => {
    const rows = css('02-queue-toolbar-rows.css')
    expect(rows).toMatch(/\.tile\.wh-dlt \{[^}]*border-color: var\(--wh-dlt-border\)/)
    expect(rows).toMatch(/\.tile\.wh-acme \{[^}]*border-color: var\(--wh-acme-border\)/)
    const chips = css('07-calendar-queue-week.css')
    expect(chips).toMatch(/\.wh-dlt\s+\{[^}]*var\(--wh-dlt-bg\)/)
    expect(chips).toMatch(/\.wh-acme\s+\{[^}]*var\(--wh-acme-bg\)/)
  })
})
