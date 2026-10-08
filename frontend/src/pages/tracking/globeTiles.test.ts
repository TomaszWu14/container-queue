import { describe, expect, it } from 'vitest'
import { latLonToVec3 } from './globeMath'
import { capRadiusDeg, globeLevel, globeTilesFor, tilesInCap } from './globeTiles'

const R = 100

describe('globeLevel', () => {
  it('cały glob z daleka → poziom 0 (wystarcza zdjęcie 4k)', () => {
    expect(globeLevel(R * 3.1, R, 45, 900)).toBe(0)
  })
  it('maks. zbliżenie (R·1,06) → poziom 3', () => {
    expect(globeLevel(R * 1.06, R, 45, 900)).toBe(3)
  })
  it('wyższy bufor (DPR 2) podnosi poziom przy tej samej odległości', () => {
    const d = R * 1.5
    expect(globeLevel(d, R, 45, 1800)).toBeGreaterThan(globeLevel(d, R, 45, 600))
  })
})

describe('capRadiusDeg', () => {
  it('z daleka czasza = horyzont (acos R/d)', () => {
    expect(capRadiusDeg(R * 3, R, 45, 2)).toBeCloseTo(Math.acos(1 / 3) * 180 / Math.PI, 5)
  })
  it('przy maks. zbliżeniu kadr obejmuje tylko kilka stopni', () => {
    const c = capRadiusDeg(R * 1.06, R, 45, 2)
    expect(c).toBeGreaterThan(1)
    expect(c).toBeLessThan(6)
  })
})

describe('tilesInCap', () => {
  it('Słowenia (46°N, 15°E), czasza 3° na z3 → kafelek pod spodem pierwszy', () => {
    const tiles = tilesInCap(3, 46, 15, 3)
    // z3: 11,25° na kafelek → wiersz floor((90-46)/11,25)=3, kolumna floor(195/11,25)=17
    expect(tiles[0]).toEqual({ z: 3, row: 3, col: 17 })
    expect(tiles.length).toBeLessThanOrEqual(6)
  })
  it('zawija się przez antymerydian (Fidżi 179,9°E łapie kolumnę zachodnią)', () => {
    const cols = tilesInCap(3, -17, 179.9, 3).map(t => t.col)
    expect(cols).toContain(31)
    expect(cols).toContain(0)
  })
})

describe('globeTilesFor', () => {
  it('z daleka → brak łat', () => {
    expect(globeTilesFor(latLonToVec3(46, 15, R * 3.1), R, 45, 2, 900)).toEqual([])
  })
  it('zbliżenie nad Słowenią → z3, mało kafelków, pierwszy pod kamerą', () => {
    const tiles = globeTilesFor(latLonToVec3(46, 15, R * 1.06), R, 45, 2, 900)
    expect(tiles[0]).toEqual({ z: 3, row: 3, col: 17 })
    expect(tiles.every(t => t.z === 3)).toBe(true)
    expect(tiles.length).toBeLessThanOrEqual(24)
  })
})
