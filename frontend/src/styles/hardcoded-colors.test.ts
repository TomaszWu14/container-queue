// Strażnik kolorów na sztywno (ciemny motyw, audyt UI 2026-09-27): kolor w regule CSS albo w stylu
// inline musi pochodzić z tokena (var(--…)), bo tylko tokeny mają wariant ciemny. Pliki z dawnymi
// hexami są w hardcoded-colors.baseline.json i mogą je tylko USUWAĆ (zapadka jak limit 500 linii).
// Po sprzątaniu obniż wpis:  UPDATE_COLOR_BASELINE=1 npx vitest run src/styles/hardcoded-colors.test.ts
import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { expect, it } from 'vitest'

const SRC = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const BASELINE = new URL('./hardcoded-colors.baseline.json', import.meta.url)
const HEX = /#[0-9a-fA-F]{3,8}\b/g
// definicje tokenów (--nazwa: wartość) to jedyne dozwolone miejsce na hex
const TOKEN_DECL = /--[\w-]+\s*:[^;{}]*/g
const SKIP = new Set(['styles/00-tokens.css'])   // generowany z audit/design-system/tokens.py

export function countHex(file: string, text: string): number {
  if (file.endsWith('.css')) {
    const rules = text.replace(/\/\*[\s\S]*?\*\//g, '').replace(TOKEN_DECL, '')
    return rules.match(HEX)?.length ?? 0
  }
  // TS/TSX: hex jako literał łańcucha ('#fff' w style={{…}}, kolory map/wykresów)
  return text.match(/['"`]#[0-9a-fA-F]{3,8}['"`]/g)?.length ?? 0
}

function scan(): Record<string, number> {
  const out: Record<string, number> = {}
  for (const entry of readdirSync(SRC, { recursive: true }) as string[]) {
    const file = relative(SRC, join(SRC, entry)).split(sep).join('/')
    if (!/\.(css|tsx?)$/.test(file) || /\.test\.tsx?$/.test(file) || SKIP.has(file)) continue
    const n = countHex(file, readFileSync(join(SRC, entry), 'utf-8'))
    if (n) out[file] = n
  }
  return Object.fromEntries(Object.entries(out).sort(([a], [b]) => a.localeCompare(b)))
}

it('reguły CSS i style inline nie dokładają kolorów na sztywno (tylko var(--…))', () => {
  const now = scan()
  if (process.env.UPDATE_COLOR_BASELINE) writeFileSync(BASELINE, JSON.stringify(now, null, 2) + '\n')
  const base: Record<string, number> = JSON.parse(readFileSync(BASELINE, 'utf-8'))
  const worse = Object.entries(now).filter(([f, n]) => n > (base[f] ?? 0))
    .map(([f, n]) => `${f}: ${n} (limit ${base[f] ?? 0}) — użyj tokena var(--…) z 00-tokens.css`)
  const stale = Object.entries(base).filter(([f, n]) => (now[f] ?? 0) < n)
    .map(([f, n]) => `${f}: ${now[f] ?? 0} < ${n} — obniż wpis (UPDATE_COLOR_BASELINE=1)`)
  expect(worse, 'nowe kolory na sztywno').toEqual([])
  expect(stale, 'baseline do obniżenia').toEqual([])
})

it('licznik: hex w deklaracji tokena i komentarzu się nie liczy, w regule — tak', () => {
  expect(countHex('a.css', ':root { --x: #fff; --y: #000 }\n/* #abc */ .a { color: #123456; }')).toBe(1)
  expect(countHex('a.tsx', "style={{ background: '#eef2f7', color: 'var(--text)' }}")).toBe(1)
})
