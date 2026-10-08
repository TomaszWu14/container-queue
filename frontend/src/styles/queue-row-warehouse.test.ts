// Strażnik kontrastu tła wiersza kolejki wg magazynu (--kq-row-*): tekst (--text) i teksty wtórne
// (--muted) mają ≥4.5:1 (WCAG AA) na tle i na hoverze — w jasnym i ciemnym motywie.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { tokens } from './tokenMap'

const css = (f: string) => readFileSync(new URL(`./${f}`, import.meta.url), 'utf-8')
const rows = css('11-kolejka-enterprise.css')
const dark = (s: string) => s.slice(s.indexOf(":root[data-theme='dark'] {"))
const token = (s: string, name: string) => s.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`))![1]

const lum = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const contrast = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}
const BG = ['--kq-row-dlt', '--kq-row-dlt-hover', '--kq-row-acme', '--kq-row-acme-hover']

describe('tło wiersza kolejki wg magazynu', () => {
  it.each([['jasny', (s: string) => s], ['ciemny', dark]])('motyw %s: tekst ≥4.5:1', (_, pick) => {
    for (const bg of BG) for (const fg of ['--text', '--muted']) {
      const t = tokens(pick === dark ? 'dark' : 'light')
      expect(contrast(t[fg], token(pick(rows), bg)), `${fg} na ${bg}`).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('wiersz bez magazynu nie dostaje odcienia, hover ciemnieje w odcieniu magazynu', () => {
    // bez magazynu = --kq-row-none (Administracja → Kolory), domyślnie --panel (nieprzezroczyste —
    // przyklejone kolumny nie prześwitują)
    expect(rows).toMatch(/tr\.kq-row > td \{ background: var\(--kq-wh-bg, var\(--kq-row-none, var\(--panel\)\)\)/)
    expect(rows).toMatch(/\.kq-row:hover td \{ background: var\(--kq-wh-hover,/)
    expect(lum(token(rows, '--kq-row-dlt-hover'))).toBeLessThan(lum(token(rows, '--kq-row-dlt')))
    expect(lum(token(rows, '--kq-row-acme-hover'))).toBeLessThan(lum(token(rows, '--kq-row-acme')))
  })
})

describe('teksty tabeli kolejki — ciemny motyw', () => {
  const d = (name: string) => tokens('dark')[name]
  // wszystkie tła wiersza/nagłówka w dark: panel, zaznaczony (--soft), aktywny (--accent-soft),
  // nagłówki kolumn/grup (--banner-bg), odcienie magazynu i ich hover
  const bgs = [d('--panel'), d('--soft'), d('--banner-bg'), d('--accent-soft'),
    ...BG.map(bg => token(dark(rows), bg))]

  it.each([['--kq-navy', 7], ['--kq-warn-ink', 4.5], ['--kq-late-ink', 4.5]] as const)(
    '%s ≥ %s:1 na każdym tle', (fg, min) => {
      for (const bg of bgs) {
        expect(contrast(token(dark(rows), fg), bg), `${fg} na ${bg}`).toBeGreaterThanOrEqual(min)
      }
    })

  it('jasny motyw: nr kontenera ≥7:1 na tłach wierszy', () => {
    for (const bg of ['#ffffff', ...BG.map(b => token(rows, b))]) {
      expect(contrast(token(rows, '--kq-navy'), bg), `--kq-navy na ${bg}`).toBeGreaterThanOrEqual(7)
    }
  })

  it('przyklejone kolumny nie mają w dark wymuszonego --panel (zaznaczony/aktywny wiersz = tło wiersza)', () => {
    const all = rows + css('14-kolejka-odchudzenie.css')
    expect(all).not.toMatch(/data-theme='dark'\][^{]*td\.kq-(sel|c-no)[^{]*\{[^}]*background/)
  })
})
