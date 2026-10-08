// Strażnik progu „zdjęcie z daleka, wektor z bliska" (vectorMap.ts) i geometrii 2D.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  covers, flatPxPerDeg, globePxPerDeg, linesToPath, NATIVE_PX_PER_DEG, regionCanvasSize,
  regionFor, VEC_TINTS, vecTintVar, vectorMix, vectorPaths,
} from './vectorMap'

describe('vectorMix — przejście zdjęcie → wektor', () => {
  it('do 1 teksela na px ekranu tylko zdjęcie, od 2× powiększenia tylko wektor, pośrodku płynnie', () => {
    expect(vectorMix(10)).toBe(0)
    expect(vectorMix(NATIVE_PX_PER_DEG * 0.5)).toBe(0)
    expect(vectorMix(NATIVE_PX_PER_DEG)).toBe(0)
    expect(vectorMix(NATIVE_PX_PER_DEG * 2)).toBe(1)
    expect(vectorMix(NATIVE_PX_PER_DEG * 3)).toBe(1)
    const mid = vectorMix(NATIVE_PX_PER_DEG * Math.SQRT2)
    expect(mid).toBeCloseTo(0.5, 5)
    let prev = 0
    for (let k = 1; k <= 2; k += 0.05) {
      const m = vectorMix(NATIVE_PX_PER_DEG * k)
      expect(m).toBeGreaterThanOrEqual(prev)
      prev = m
    }
    expect(vectorMix(0)).toBe(0)
    expect(vectorMix(NaN)).toBe(0)
  })

  it('widok całej Europy / Morza Północnego (~40° na 1200 px, dpr 1,5) zostaje zdjęciem', () => {
    // 1000/360·40 ≈ 111 jednostek świata szerokości kadru → 45 px/° < 60 px/° natywnych
    expect(vectorMix(flatPxPerDeg(1000 / 360 * 40, 1200, 1.5))).toBe(0)
    // zbliżenie na Niemcy/Beneluks (~8° na 1400 px, dpr 2) = już wektor
    expect(vectorMix(flatPxPerDeg(1000 / 360 * 8, 1400, 2))).toBe(1)
  })

  it('mapa 2D: cały świat = zdjęcie, zoom ×64 na ekranie 1200 px = wektor; dpr podnosi gęstość', () => {
    expect(vectorMix(flatPxPerDeg(1000, 1200))).toBe(0)
    expect(vectorMix(flatPxPerDeg(1000 / 64, 1200))).toBe(1)
    expect(flatPxPerDeg(100, 1000, 2)).toBeCloseTo(2 * flatPxPerDeg(100, 1000), 9)
    expect(flatPxPerDeg(0, 1000)).toBe(0)
  })

  it('globus: z odległości 3R zdjęcie, tuż nad powierzchnią wektor', () => {
    expect(vectorMix(globePxPerDeg(300, 100, 45, 600))).toBe(0)
    expect(vectorMix(globePxPerDeg(106, 100, 45, 600))).toBe(1)
  })
})

describe('kolory trybu wektorowego', () => {
  it('odcienie państw: tokeny 1..6, sąsiedzi DE/NL/PL/CZ różni', () => {
    const t = (id: number) => vecTintVar({ id, name: 'x' })
    expect(new Set([4, 8, 276, 528, 616, 203, 826, 250].map(t)).size).toBeGreaterThan(3)
    expect(new Set([t(276), t(528), t(616)]).size).toBe(3)
    expect(t(203)).not.toBe(t(276))
    expect(vecTintVar({ id: NaN, name: 'Kosovo' })).toMatch(/^--map-vec-tint-[1-6]$/)
  })

  it('VEC_TINTS = liczba tokenów --map-vec-tint-N w CSS (oba motywy)', () => {
    const css = readFileSync(new URL('../../styles/04-tracking-avizo-menus.css', import.meta.url), 'utf-8')
    const ids = [...css.matchAll(/--map-vec-tint-(\d+):/g)].map(m => Number(m[1]))
    expect(new Set(ids)).toEqual(new Set(Array.from({ length: VEC_TINTS }, (_, i) => i + 1)))
    expect(ids.length).toBe(2 * VEC_TINTS)
  })

  it('odcienie lądu i krajów na trasie nigdy nie są niebieskie (oba motywy), morze jest', () => {
    const css = readFileSync(new URL('../../styles/04-tracking-avizo-menus.css', import.meta.url), 'utf-8')
    const rgb = (v: string) => v.startsWith('#')
      ? [1, 3, 5].map(i => parseInt(v.slice(i, i + 2), 16))
      : v.match(/\d+/g)!.slice(0, 3).map(Number)
    const decl = [...css.matchAll(/--map-vec-(tint-\d|hl-\w+|land|sea):\s*([^;]+);/g)]
    expect(decl.length).toBe(2 * (6 + 3 + 2))
    for (const [, name, val] of decl) {
      const [r, , b] = rgb(val.trim())
      if (name === 'sea') expect(b, name).toBeGreaterThan(r + 30)
      else expect(b, `${name}: ${val}`).toBeLessThanOrEqual(r)
    }
  })
})

describe('geometria wektorowa', () => {
  it('linesToPath: skok przez antymerydian zaczyna nowy odcinek', () => {
    expect(linesToPath([[[170, 0], [179, 0], [-179, 0]]])).toBe('M972.22,250.00L997.22,250.00M2.78,250.00')
  })

  it('wybrzeże i granice 50m: niepuste, liczone raz (ten sam obiekt)', () => {
    const v = vectorPaths()
    expect(v.coast.length).toBeGreaterThan(100_000)
    expect(v.borders.length).toBeGreaterThan(10_000)
    expect(v.coast).not.toMatch(/NaN/)
    expect(vectorPaths()).toBe(v)
  })

  it('regionFor/covers: region z zapasem obejmuje kadr, także po przejściu antymerydianu', () => {
    const need = regionFor(45, 15, 5, 1)
    const drawn = regionFor(45, 15, 5)
    expect(covers(drawn, need)).toBe(true)
    expect(covers(need, regionFor(45, 25, 5, 1))).toBe(false)
    expect(covers(regionFor(0, 179, 5), regionFor(0, -179, 3, 1))).toBe(true)
    expect(regionFor(88, 0, 5).lonMax - regionFor(88, 0, 5).lonMin).toBe(360)
  })

  it('regionCanvasSize: rozdzielczość ekranu, ograniczona do maxSide z zachowaniem proporcji', () => {
    const r = { lonMin: 0, lonMax: 10, latMin: -5, latMax: 5 }
    expect(regionCanvasSize(r, 100, 4096)).toEqual({ w: 1000, h: 1000 })
    const big = regionCanvasSize(r, 1000, 4096)
    expect(Math.max(big.w, big.h)).toBe(4096)
    expect(big.w).toBe(big.h)
  })
})
