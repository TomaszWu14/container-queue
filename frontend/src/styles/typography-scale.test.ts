// Strażnik UX-008 (audyt UI S13): nagłówki bez reguły brały domyślne rozmiary przeglądarki
// (h3 = 18,72 px, h1 = 32 px), a liczby/daty w tabelach nie miały cyfr tabelarycznych —
// kolumny „tańczyły”. Skala --fs-* i tabular-nums muszą być ustawione globalnie.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const tokens = readFileSync(new URL('./00-tokens.css', import.meta.url), 'utf-8')
const base = readFileSync(new URL('./01-tokens-base.css', import.meta.url), 'utf-8')

describe('skala typograficzna', () => {
  it('tokeny --fs-xs…--fs-2xl istnieją', () => {
    for (const k of ['xs', 'sm', 'base', 'md', 'lg', 'xl', '2xl']) {
      expect(tokens).toMatch(new RegExp(`--fs-${k}:\\s*\\d+px`))
    }
  })
  it('h1/h2/h3 biorą rozmiar ze skali, nie z domyślnych przeglądarki', () => {
    expect(base).toMatch(/h1 \{[^}]*font-size: var\(--fs-xl\)/)
    expect(base).toMatch(/h2 \{[^}]*font-size: var\(--fs-lg\)/)
    expect(base).toMatch(/h3 \{[^}]*font-size: var\(--fs-md\)/)
    // numer kontenera jako tytuł nie może zmaleć (zrzuty przed/po 2026-09-28: 21 px → 18 px)
    expect(base).toMatch(/h2\.mono \{ font-size: var\(--fs-xl\); \}/)
  })
  it('tabele, .mono i <time> mają cyfry tabelaryczne', () => {
    expect(base).toMatch(/table, \.mono, time \{ font-variant-numeric: tabular-nums; \}/)
  })
})
