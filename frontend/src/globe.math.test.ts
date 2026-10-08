// @vitest-environment jsdom
// Matematyka globusa 3D: lat/lon→wektor, wielki okrąg (antymerydian!),
// culling horyzontu, terminator, rozrzedzanie etykiet, tryb mapy w localStorage.
import { afterEach, describe, expect, it } from 'vitest'
import {
  greatCirclePoints, isFrontFacing, latLonToVec3, readMapMode, storeMapMode,
  sunDirection, thinByDistance,
} from './pages/tracking/globeMath'

const len = (v: number[]) => Math.hypot(v[0], v[1], v[2])

describe('latLonToVec3', () => {
  it('bieguny i równik na promieniu r', () => {
    expect(latLonToVec3(90, 0, 5)[1]).toBeCloseTo(5)
    expect(latLonToVec3(-90, 0, 5)[1]).toBeCloseTo(-5)
    const eq = latLonToVec3(0, 0, 1)
    expect(eq[1]).toBeCloseTo(0)
    expect(len(eq)).toBeCloseTo(1)
  })
  it('lon 0 i lon 180 są antypodalne w płaszczyźnie równika', () => {
    const a = latLonToVec3(0, 0), b = latLonToVec3(0, 180)
    expect(a[0]).toBeCloseTo(-b[0])
    expect(a[2]).toBeCloseTo(-b[2])
  })
})

describe('greatCirclePoints', () => {
  it('wszystkie punkty leżą na sferze, segmentacja co ~2°', () => {
    const pts = greatCirclePoints([0, 0], [0, 90], 2, 100)
    // 90° łuku / 2° = 45 segmentów → 46 punktów
    expect(pts.length).toBe(46)
    for (const p of pts) expect(len(p)).toBeCloseTo(100, 5)
  })
  it('antymerydian: trasa 170°E → 170°W idzie krótszą drogą (przez 180°)', () => {
    const pts = greatCirclePoints([10, 170], [10, -170], 2, 1)
    // krótka droga = ~20° łuku → ~11 punktów, NIE ~340° w poprzek mapy
    expect(pts.length).toBeLessThan(15)
    // punkt środkowy blisko lon 180 (x ~ dodatni w naszej konwencji, |z| małe? —
    // wystarczy: każdy punkt w promieniu 20° od punktu startowego)
    const start = latLonToVec3(10, 170)
    for (const p of pts) {
      const dot = p[0] * start[0] + p[1] * start[1] + p[2] * start[2]
      expect(Math.acos(Math.min(1, dot))).toBeLessThan(21 * Math.PI / 180)
    }
  })
  it('punkty identyczne — bez NaN, zwraca końce', () => {
    const pts = greatCirclePoints([50, 20], [50, 20], 2, 1)
    expect(pts.length).toBe(2)
    expect(pts.flat().every(Number.isFinite)).toBe(true)
  })
})

describe('isFrontFacing (culling horyzontu)', () => {
  const cam: [number, number, number] = [0, 0, 300]   // kamera nad lon -90? — patrzy na +z
  it('punkt po stronie kamery widoczny, antypodalny nie', () => {
    expect(isFrontFacing([0, 0, 100], cam, 100)).toBe(true)
    expect(isFrontFacing([0, 0, -100], cam, 100)).toBe(false)
  })
  it('punkt dokładnie na "krawędzi" kuli (90°) — za horyzontem przy skończonej odległości', () => {
    expect(isFrontFacing([100, 0, 0], cam, 100)).toBe(false)
  })
})

describe('sunDirection', () => {
  it('wektor jednostkowy; w południe UTC słońce nad okolicą Greenwich', () => {
    const v = sunDirection(new Date(Date.UTC(2026, 2, 21, 12, 0, 0)))   // równonoc, 12 UTC
    expect(len(v)).toBeCloseTo(1)
    // lon≈0, lat≈0 → wektor ≈ latLonToVec3(0, 0)
    const ref = latLonToVec3(0, 0)
    const dot = v[0] * ref[0] + v[1] * ref[1] + v[2] * ref[2]
    expect(dot).toBeGreaterThan(0.99)
  })
})

describe('thinByDistance', () => {
  it('usuwa punkty bliżej niż minDeg, pierwszy wygrywa', () => {
    const kept = thinByDistance(
      [{ lat: 0, lon: 0 }, { lat: 0.5, lon: 0.5 }, { lat: 10, lon: 10 }], 2)
    expect(kept).toEqual([0, 2])
  })
})

describe('tryb mapy 2D/3D (localStorage)', () => {
  afterEach(() => localStorage.clear())
  it('domyślnie 3D', () => expect(readMapMode()).toBe('3d'))
  it('zapamiętuje wybór 2D', () => {
    storeMapMode('2d')
    expect(readMapMode()).toBe('2d')
    storeMapMode('3d')
    expect(readMapMode()).toBe('3d')
  })
})

import { VIEW_PRESETS } from './pages/tracking/globeMath'

describe('VIEW_PRESETS — presety widoku globu', () => {
  it('ma 4 regiony z sensownymi współrzędnymi i dystansem (bliżej = mniejszy distMul)', () => {
    const keys = Object.keys(VIEW_PRESETS)
    expect(keys).toEqual(['europe', 'asia', 'suez', 'globe'])
    for (const p of Object.values(VIEW_PRESETS)) {
      expect(p.lat).toBeGreaterThanOrEqual(-90); expect(p.lat).toBeLessThanOrEqual(90)
      expect(p.lon).toBeGreaterThanOrEqual(-180); expect(p.lon).toBeLessThanOrEqual(180)
      expect(p.distMul).toBeGreaterThan(1)   // >1 promienia = poza powierzchnią
    }
    // Suez najbliżej, „cały glob" najdalej
    expect(VIEW_PRESETS.suez.distMul).toBeLessThan(VIEW_PRESETS.globe.distMul)
  })
})
