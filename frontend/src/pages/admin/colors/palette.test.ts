// Paleta i kolory domyślne edytora kolorów: 500 barw, każdy edytowalny token ma domyślny #rrggbb
// w obu motywach (czytany z arkuszy — rozjazd nazwy tokena = szary zamiast prawdziwego koloru).
import { describe, expect, it, vi } from 'vitest'

// vitest podaje arkusze CSS jako puste (css: stub) — w teście treść prosto z dysku, w buildzie ?raw z Vite
const { disk } = vi.hoisted(() => ({ disk: (f: string) => async () => ({
  default: (await import('node:fs')).readFileSync(new URL(`../../../styles/${f}`, import.meta.url), 'utf-8') }) }))
vi.mock('../../../styles/00-tokens.css?raw', disk('00-tokens.css'))
vi.mock('../../../styles/11-kolejka-enterprise.css?raw', disk('11-kolejka-enterprise.css'))
import { GROUPS, TOKENS, contrast, defaults, hsl, palette } from './palette'

describe('palette', () => {
  it('500 kolorów w siatce 25 × 20, wszystkie #rrggbb', () => {
    const grid = palette()
    expect(grid).toHaveLength(25)
    expect(grid.every(row => row.length === 20)).toBe(true)
    expect(grid.flat().every(c => /^#[0-9a-f]{6}$/.test(c))).toBe(true)
    expect(new Set(grid.flat()).size).toBeGreaterThan(450)
  })

  it('domyślne z arkuszy dla każdego tokenu w obu motywach; ciemny ≠ jasny', () => {
    for (const mode of ['light', 'dark'] as const) {
      const d = defaults(mode)
      expect(Object.keys(d).sort()).toEqual([...TOKENS].sort())
      expect(Object.values(d).every(c => /^#[0-9a-f]{6}$/.test(c))).toBe(true)
      expect(d['--kq-row-none']).toBe(d['--panel'])            // wiersz bez magazynu = panel (jak dziś)
    }
    expect(defaults('dark')['--bg']).not.toBe(defaults('light')['--bg'])
    expect(defaults('dark')['--kq-row-dlt']).not.toBe(defaults('light')['--kq-row-dlt'])
    // brak odczytu dałby szary zastępczy — żaden token nie może na nim wylądować
    for (const mode of ['light', 'dark'] as const) expect(Object.values(defaults(mode))).not.toContain(hsl(0, 0, 0.5))
  })

  it('kontrast WCAG i unikalne klucze grup', () => {
    expect(contrast('#000000', '#ffffff')).toBeCloseTo(21, 0)
    expect(new Set(GROUPS.map(g => g.key)).size).toBe(GROUPS.length)
  })
})
