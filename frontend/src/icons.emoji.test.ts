// Strażnik audytu UI (PR 6): ikony to Lucide, nie emoji. Poza komentarzami w kodzie nie ma
// piktogramów emoji ani symboli-ikon (★ ☆ ✕ ✎ ⚠ ▲ ▼ ▸ ▾ ✉ ⬇). Wyjątek: etykiety rysowane na canvasie
// globusa (tam nie da się wstawić SVG). Strzałki → i ✓ w zdaniach to typografia — dozwolone.
import { describe, expect, it } from 'vitest'

const sources = import.meta.glob(['./**/*.ts', './**/*.tsx', '!./**/*.test.*'],
  { query: '?raw', import: 'default', eager: true }) as Record<string, string>

const ICONLIKE = /[\u{1F300}-\u{1FAFF}★☆✕✎✏⚠▲▼▸▾▴✉⬇✖✗✅🚫]/u
const ALLOW = new Set(['./pages/tracking/GlobeView.tsx'])

describe('ikony — Lucide zamiast emoji', () => {
  it('brak emoji/symboli-ikon poza komentarzami', () => {
    const offenders: string[] = []
    for (const [path, src] of Object.entries(sources)) {
      if (ALLOW.has(path)) continue
      src.split('\n').forEach((line, i) => {
        const code = line.replace(/\/\/.*|\/\*.*?\*\/|\{\/\*.*?\*\/\}/g, '')
        if (!/^\s*\*/.test(line) && ICONLIKE.test(code)) offenders.push(`${path}:${i + 1}`)
      })
    }
    expect(offenders).toEqual([])
  })
})
