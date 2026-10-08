// Tabela kolejki (decyzja 2026-09-28, wariant B): cienka siatka pion+poziom i przewijanie
// przyciągane do pełnych wierszy pod przyklejonymi nagłówkami (kolumn 26px + dnia 28px) —
// wiersz nie wchodzi w połowie pod pasek sum dnia i obraz nie „skacze”.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = (f: string) => readFileSync(new URL(`./${f}`, import.meta.url), 'utf-8')
const ent = css('11-kolejka-enterprise.css')
const slim = css('14-kolejka-odchudzenie.css')

describe('siatka i przewijanie kolejki', () => {
  it('pionowe i poziome linie komórek z tokenu --kq-grid (jasny i ciemny motyw)', () => {
    expect(ent).toMatch(/\.kq-table td, \.kq-table th \{ border-right: 1px solid var\(--kq-grid\)/)
    expect(ent.match(/--kq-grid:\s*#[0-9a-f]{6}/gi)).toHaveLength(2)
  })

  it('przewijanie przyciąga do wiersza tuż pod nagłówkami (26 + 28 px)', () => {
    const sticky = Number(slim.match(/\.kq-table th \{ height: (\d+)px/)![1])
      + Number(slim.match(/\.kq-ghead > td \{ position: sticky; top: \d+px; z-index: 2; height: (\d+)px/)![1])
    expect(slim).toMatch(/scroll-snap-type: y proximity/)
    expect(slim).toContain(`scroll-padding-top: ${sticky}px`)
    expect(slim).toMatch(/tr\.kq-row, \.kq-table tr\.kq-ghead \{ scroll-snap-align: start/)
  })

  it('pasek grupy przyklejony do lewej przy przewijaniu w poziomie, na nieprzezroczystym tle z tokenu', () => {
    // sticky left:0 na wewnętrznym divie; bez width: max-content div wypełnia td (colSpan) i nie ma gdzie się przesunąć,
    // a overflow:hidden z `.kq-table td` robi z td kontener przewijania i sticky przestaje działać
    expect(ent).toMatch(/\.kq-ghead-in \{ position: sticky; left: 0;/)
    expect(slim).toMatch(/\.kq-ghead > td \{ position: sticky;[^}]*overflow: visible; \}/)
    expect(slim).toMatch(/\.kq-ghead-in \{ width: max-content;/)
    expect(ent).toMatch(/\[data-theme='dark'\] \.kq-ghead > td \{ background: var\(--/)
  })
})
