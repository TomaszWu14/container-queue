// @vitest-environment jsdom
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { LangContext, localeFor, useLocale, type Lang } from './i18n'

const wrap = (lang: Lang) => ({ children }: { children: ReactNode }) =>
  <LangContext.Provider value={{ lang, setLang: () => {} }}>{children}</LangContext.Provider>

describe('localeFor / useLocale — jedno źródło locale', () => {
  it('mapuje języki UI, nieznany → pl-PL', () => {
    expect(localeFor('en')).toBe('en-GB')
    expect(localeFor('pt')).toBe('pt-PT')
    expect(localeFor('xx')).toBe('pl-PL')
  })
  it('useLocale bierze język z kontekstu', () => {
    expect(renderHook(() => useLocale(), { wrapper: wrap('pt') }).result.current).toBe('pt-PT')
    expect(renderHook(() => useLocale(), { wrapper: wrap('en') }).result.current).toBe('en-GB')
  })
})

// strażnik: żadnych lokalnych map LOCALE ani 'pl-PL' na sztywno poza świadomymi wyjątkami
// (formatNum = konwencja suity, zegar 24h, landing przed logowaniem jest po polsku)
const ALLOWED = new Set(['i18n.ts', 'dates.ts', 'clock.tsx', join('pages', 'LandingPage.tsx')])
const walk = (dir: string): string[] => readdirSync(dir).flatMap(f => {
  const p = join(dir, f)
  return statSync(p).isDirectory() ? walk(p) : /\.tsx?$/.test(f) && !/\.test\./.test(f) ? [p] : []
})

it("brak zduplikowanych map locale i 'pl-PL' na sztywno", () => {
  const root = join(__dirname)
  const bad = walk(root)
    .filter(p => !ALLOWED.has(p.slice(root.length + 1)))
    .filter(p => /'pl-PL'|en-GB|toLocaleString\(\)/.test(readFileSync(p, 'utf-8')))
    .map(p => p.slice(root.length + 1))
  expect(bad).toEqual([])
})
