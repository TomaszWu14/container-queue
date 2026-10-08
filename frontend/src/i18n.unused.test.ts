// Strażnik martwych kluczy i18n (audyt 2026-09-23, P14): każdy klucz słownika musi mieć
// użycie w kodzie — dosłowne (t('klucz'), 'klucz' w mapie) albo przez dynamiczny prefiks
// (t(`invStatus_${x}`), 'st_' + x). Klucze składane w backendzie (np. sigSum_*) też się liczą.
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { DICTS } from './i18n'

function walk(dir: string, ext: RegExp, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = `${dir}/${name}`
    if (statSync(p).isDirectory()) { if (name !== 'i18n' && name !== 'node_modules') walk(p, ext, out) }
    else if (ext.test(name) && !name.includes('.test.') && name !== 'i18n.ts') out.push(p)
  }
  return out
}

describe('i18n: brak nieużywanych kluczy', () => {
  it('każdy klucz pl ma użycie w kodzie', () => {
    const files = walk(`${process.cwd()}/src`, /\.tsx?$/)
    const backend = `${process.cwd()}/../backend/app`
    if (existsSync(backend)) walk(backend, /\.py$/, files)
    const code = files.map(f => readFileSync(f, 'utf-8')).join('\n')
    const words = new Set(code.match(/[A-Za-z_][A-Za-z0-9_]*/g))
    const prefixes = [
      ...[...code.matchAll(/`([A-Za-z_][A-Za-z0-9_]*)\$\{/g)].map(m => m[1]),
      ...[...code.matchAll(/['"]([A-Za-z_][A-Za-z0-9_]*)['"]\s*\+/g)].map(m => m[1]),
      ...[...code.matchAll(/f['"]([A-Za-z_][A-Za-z0-9_]*)\{/g)].map(m => m[1]),
    ]
    const unused = Object.keys(DICTS.pl).filter(k => !words.has(k) && !prefixes.some(p => k.startsWith(p)))
    expect(unused).toEqual([])
  })
})
