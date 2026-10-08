// Strażnik trybu ciemnego dla pigułek i przycisku „usuń” (audyt UI A8/B29 — UX-021, UX-030): chipy
// odprawy/dokumentów/zakupów, „Specjalna troska” i .btn.danger biorą tło i tekst z tokenów, więc w dark
// mode mają ciemne tło (nie pastelowo-białą plamę na granacie) i czytelny tekst (AA 4.5:1) w obu motywach.
import { describe, expect, it } from 'vitest'
import { readAppCss } from '../appCss.testutil'
import { tokens } from './tokenMap'

const SELECTOR = /^\.badge\.(?:cs|ds|ps)-[A-Z_]+$|^\.badge\.special$|^\.btn\.danger$/

function lum(hex: string): number {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const contrast = (a: string, b: string) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

// reguły „selektor { … background: X; color: Y }” (bez komentarzy, pojedyncze selektory)
function chips(): { sel: string; bg: string; fg: string }[] {
  const css = readAppCss().replace(/\/\*[\s\S]*?\*\//g, '')
  const out: { sel: string; bg: string; fg: string }[] = []
  for (const m of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
    const sel = m[1].trim()
    if (!SELECTOR.test(sel)) continue
    const decl = (p: string) => m[2].match(new RegExp(`(?:^|;)\\s*${p}\\s*:\\s*([^;]+)`))?.[1].trim()
    const bg = decl('background'), fg = decl('color')
    if (bg && fg) out.push({ sel, bg, fg })
  }
  return out
}

function value(v: string, theme: 'light' | 'dark'): string {
  const ref = v.match(/^var\(\s*(--[\w-]+)\s*\)$/)
  return ref ? tokens(theme)[ref[1]] ?? v : v
}

describe('pigułki i „usuń” w trybie ciemnym', () => {
  const rules = chips()

  it('znajduje reguły chipów (odprawa, dokumenty, zakupy, specjalna, przycisk usuń)', () => {
    const sels = rules.map(r => r.sel)
    for (const s of ['.badge.cs-ZLECONA', '.badge.ds-WYSLANE', '.badge.ps-WSTRZYMANE', '.badge.special', '.btn.danger'])
      expect(sels).toContain(s)
  })

  it('dark: ciemne tło z tokena i tekst AA — żadnej jasnej plamy', () => {
    const bad = rules.flatMap(({ sel, bg, fg }) => {
      const b = value(bg, 'dark'), f = value(fg, 'dark')
      if (!/^#[0-9a-f]{6}$/.test(b) || !/^#[0-9a-f]{6}$/.test(f)) return [`${sel}: ${bg} / ${fg} bez tokena`]
      const issues = []
      if (lum(b) > 0.08) issues.push(`${sel}: jasne tło ${b} w dark`)
      if (contrast(b, f) < 4.5) issues.push(`${sel}: kontrast ${contrast(b, f).toFixed(2)} w dark`)
      return issues
    })
    expect(bad).toEqual([])
  })

  it('light: tekst AA na tle chipa', () => {
    const bad = rules.filter(({ bg, fg }) => contrast(value(bg, 'light'), value(fg, 'light')) < 4.5)
      .map(r => r.sel)
    expect(bad).toEqual([])
  })
})
