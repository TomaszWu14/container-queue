// Strażnik: klasa aplikacji „grid” na <table> koliduje z utility Tailwinda .grid { display: grid }
// (tabela staje się siatką CSS, nagłówki rozjeżdżają się z kolumnami). table.grid musi jawnie
// wymuszać display: table — audyt UI 2026-09-27.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

describe('table.grid', () => {
  it('wymusza display: table (kolizja z utility Tailwinda .grid)', () => {
    const css = readFileSync(new URL('./04-tracking-avizo-menus.css', import.meta.url), 'utf-8')
    expect(css).toMatch(/table\.grid \{ display: table;/)
  })
})
