// UX-040 (audyt UI S15): ustawienie systemowe „ogranicz ruch” — CSS globalnie + pętle/przewijanie w JS.
import { readFileSync } from 'node:fs'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { prefersReducedMotion, scrollBehavior } from './motion'

const mockMatch = (matches: boolean) =>
  vi.stubGlobal('matchMedia', vi.fn((q: string) => ({ matches: q === '(prefers-reduced-motion: reduce)' && matches })))

afterEach(() => vi.unstubAllGlobals())

describe('prefersReducedMotion', () => {
  it('true gdy system prosi o ograniczenie ruchu', () => {
    mockMatch(true)
    expect(prefersReducedMotion()).toBe(true)
    expect(scrollBehavior()).toBe('auto')
  })
  it('false domyślnie — płynne przewijanie zostaje', () => {
    mockMatch(false)
    expect(prefersReducedMotion()).toBe(false)
    expect(scrollBehavior()).toBe('smooth')
  })
  it('false bez matchMedia (stare środowisko / SSR)', () => {
    vi.stubGlobal('matchMedia', undefined)
    expect(prefersReducedMotion()).toBe(false)
  })
})

describe('globalny CSS', () => {
  it('00-tokens.css wygasza animacje i przejścia przy prefers-reduced-motion', () => {
    const css = readFileSync(new URL('./styles/00-tokens.css', import.meta.url), 'utf-8')
    const block = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
    expect(block).toMatch(/\*, \*::before, \*::after \{[^}]*animation-duration: 0\.01ms !important;[^}]*animation-iteration-count: 1 !important;[^}]*transition-duration: 0\.01ms !important;[^}]*scroll-behavior: auto !important;/)
  })
})

// CSS scroll-behavior nie nadpisuje jawnego { behavior: 'smooth' } ani pętli rAF — stąd helper w JS
describe('miejsca w JS respektują helper', () => {
  it.each([
    'pages/LandingPage.tsx', 'pages/ContainerPage.tsx', 'pages/queue/useSearchFocus.ts',
    'pages/tracking/VesselsTable.tsx', 'pages/tracking/GlobeView.tsx', 'pages/ContainerPacking.tsx',
  ])('%s', (f) => {
    const src = readFileSync(new URL('./' + f, import.meta.url), 'utf-8')
    expect(src).not.toMatch(/behavior: 'smooth'/)
    expect(src).toMatch(/prefersReducedMotion\(\)|scrollBehavior\(\)/)
  })
})
