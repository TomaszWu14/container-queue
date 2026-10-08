// Strażnik UX-042: tabele danych używają wspólnej klasy `grid` (table.grid w styles/04-*.css).
// Nieistniejąca klasa „table” albo samo „dict-table” (reguły są tylko dla table.grid.dict-table)
// dawały surową, nieostylowaną tabelę (Dziennik zmian, DLT, Dostawca, Reguły powiadomień).
import { describe, expect, it } from 'vitest'

const sources = import.meta.glob(['./**/*.tsx', '!./**/*.test.tsx'],
  { query: '?raw', import: 'default', eager: true }) as Record<string, string>

// tabele z własnym, celowo innym stylem (nie tabela danych)
const OWN_STYLED = new Set(['vc-items'])

describe('klasa tabel', () => {
  it('każda <table className="…"> ma klasę grid (albo własny styl z listy)', () => {
    const bad: string[] = []
    for (const [file, src] of Object.entries(sources)) {
      for (const m of src.matchAll(/<table className="([^"]*)"/g)) {
        const cls = m[1].split(/\s+/)
        if (!cls.includes('grid') && !cls.some(c => OWN_STYLED.has(c))) bad.push(`${file}: "${m[1]}"`)
      }
    }
    expect(bad).toEqual([])
  })
})
