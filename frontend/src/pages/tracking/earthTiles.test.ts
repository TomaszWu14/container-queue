import { describe, expect, it } from 'vitest'
import { visibleTiles } from './earthTiles'

describe('visibleTiles', () => {
  it('cały świat na zwykłym ekranie — wystarcza zdjęcie bazowe (brak kafelków)', () => {
    expect(visibleTiles({ x: 0, y: 0, w: 1000 }, 500, 1400)).toEqual([])
  })

  it('średni zoom → poziom 1 (kafelek 125 j.), tylko kafelki w kadrze', () => {
    // 1400 px na 200 j. = 7 px/j. → z1 (8,19 px/j.)
    const tiles = visibleTiles({ x: 100, y: 50, w: 200 }, 100, 1400)
    expect(tiles.every(t => t.z === 1 && t.size === 125)).toBe(true)
    expect(tiles.map(t => `${t.row}_${t.col}`).sort()).toEqual(['0_0', '0_1', '0_2', '1_0', '1_1', '1_2'])
    expect(tiles[0].href).toMatch(/globe\/tiles\/1\/\d+_\d+\.webp$/)
  })

  it('duży zoom → poziom 2 (kafelek 62,5 j.)', () => {
    // 875 px na 50 j. = 17,5 px/j. → z2 (16,4 px/j. × 1,25 wystarcza)
    const tiles = visibleTiles({ x: 500, y: 250, w: 50 }, 25, 875)
    expect(tiles.map(t => [t.z, t.row, t.col])).toEqual([[2, 4, 8]])
    expect(tiles[0]).toMatchObject({ x: 500, y: 250, size: 62.5 })
  })

  it('maks. zoom → poziom 3 (kafelek 31,25 j.), kafelki z3 w kadrze', () => {
    // 1400 px na 62,5 j. = 22,4 px/j. → z3
    const tiles = visibleTiles({ x: 500, y: 250, w: 62.5 }, 31.25, 1400)
    expect(tiles.map(t => [t.z, t.row, t.col])).toEqual([[3, 8, 16], [3, 8, 17]])
    expect(tiles[0].href).toMatch(/globe\/tiles\/3\/8_16\.webp$/)
  })

  it('gęstość ekranu (DPR) podnosi poziom — retina potrzebuje więcej pikseli', () => {
    // 1400 px CSS na 200 j.: przy DPR 1 → z1, przy DPR 2 (14 px/j.) → z2
    expect(visibleTiles({ x: 100, y: 50, w: 200 }, 100, 1400)[0].z).toBe(1)
    expect(visibleTiles({ x: 100, y: 50, w: 200 }, 100, 1400, 2)[0].z).toBe(2)
  })

  it('poziom nigdy nie przekracza MAX_Z (3)', () => {
    expect(visibleTiles({ x: 500, y: 250, w: 10 }, 5, 4000, 3).every(t => t.z === 3)).toBe(true)
  })
})
