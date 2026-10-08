// Kolejka: kolumna wyboru (☐/☆) i Nr kontenera przyklejone do lewej przy przewijaniu w bok
// (jak „zablokuj pierwszą kolumnę" w Excelu) — na nieprzezroczystym tle wiersza z tokenów.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = (f: string) => readFileSync(new URL(`./${f}`, import.meta.url), 'utf-8')
const ent = css('11-kolejka-enterprise.css')
const slim = css('14-kolejka-odchudzenie.css')
const SEL_W = readFileSync(new URL('../pages/queue/EnterpriseTable.tsx', import.meta.url), 'utf-8')
  .match(/export const SEL_W = (\d+)/)![1]

describe('przyklejone kolumny kolejki', () => {
  it('td wyboru i Nr: sticky, left 0 i left = szerokość kolumny wyboru (SEL_W)', () => {
    expect(slim).toMatch(/:where\(\.kq-table\) td\.kq-sel, :where\(\.kq-table\) td\.kq-c-no \{ position: sticky;[^}]*z-index: 1;/)
    expect(slim).toMatch(/\.kq-table \.kq-sel \{ left: 0; \}/)
    expect(slim).toMatch(/\.kq-table \.kq-c-no, \.kq-table th\.kq-h-no \{ left: var\(--kq-sel-w\); \}/)
    expect(slim).toContain(`--kq-sel-w: ${SEL_W}px`)
  })

  it('warstwy: komórki 1 < pasek dnia 2 < nagłówki kolumn 3 < róg tabeli 4', () => {
    expect(slim).toMatch(/\.kq-ghead > td \{ position: sticky; top: 26px; z-index: 2;/)
    expect(slim).toMatch(/\.kq-table th \{ height: 26px; font-size: 10px; z-index: 3; \}/)
    expect(slim).toMatch(/\.kq-table th\.kq-sel, \.kq-table th\.kq-h-no \{ position: sticky; z-index: 4; \}/)
    expect(ent).toMatch(/\.kq-table th \{\s*position: sticky; top: 0;/)
  })

  it('tła wierszy (magazyn, bez magazynu, hover, zaznaczony, aktywny, flash) tylko z tokenów', () => {
    expect(ent).toMatch(/tr\.kq-row > td \{ background: var\(--kq-wh-bg, var\(--kq-row-none, var\(--panel\)\)\); \}/)
    expect(ent).toMatch(/\.kq-row:hover td \{ background: var\(--kq-wh-hover, var\(--kq-row-none-hover\)\); \}/)
    expect(ent).toMatch(/\.kq-row\.selected td \{ background: var\(--kq-row-sel\); \}/)
    expect(ent).toMatch(/\.kq-row\.active td \{ background: var\(--kq-row-active\); \}/)
    expect(ent).toMatch(/\.kq-row\.flash td \{ background: var\(--kq-row-active\);/)
    // każdy token tła: pełny hex (bez kanału alfa) albo token — pod przyklejonymi przewija się treść
    for (const tok of ['kq-row-dlt', 'kq-row-acme', 'kq-row-dlt-hover', 'kq-row-acme-hover',
      'kq-row-none-hover', 'kq-row-sel', 'kq-row-active']) {
      const vals = [...ent.matchAll(new RegExp(`--${tok}:\\s*([^;]+);`, 'g'))].map(m => m[1].trim())
      expect(vals, tok).toHaveLength(2)   // jasny + ciemny motyw
      for (const v of vals) expect(v, tok).toMatch(/^(#[0-9a-f]{6}|var\(--[\w-]+\))$/i)
    }
  })

  it('krawędź zamrożonego bloku: linia z --kq-grid + cień z tokenu po przewinięciu w bok', () => {
    expect(slim).toMatch(/:is\(td\.kq-c-no, th\.kq-h-no\) \{ box-shadow: inset -1px 0 0 var\(--kq-grid\); \}/)
    expect(slim).toMatch(/animation-timeline: scroll\(nearest inline\)/)
    expect(slim).toMatch(/@keyframes kq-freeze-edge \{\s*to \{ box-shadow: [^}]*var\(--kq-freeze-shadow\)/)
    expect(slim.match(/--kq-freeze-shadow:/g)).toHaveLength(2)
  })
})
