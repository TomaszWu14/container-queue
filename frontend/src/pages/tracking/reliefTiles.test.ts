// Strażnik piramidy rzeźby terenu (reliefTiles.ts): wybór poziomu i pokrycie regionu kafelkami.
import { describe, expect, it } from 'vitest'
import { reliefLevel, reliefTilesFor } from './reliefTiles'

describe('reliefTiles', () => {
  it('poziom rośnie z gęstością ekranu i kończy się na z2', () => {
    expect(reliefLevel(5)).toBe(0)
    expect(reliefLevel(4096 / 360 * 2)).toBe(1)
    expect(reliefLevel(500)).toBe(2)
  })

  it('z0 = jeden obraz świata; z2 = kafelki 22,5° pokrywające region (zawinięte przez ±180)', () => {
    const world = { lonMin: -180, lonMax: 180, latMin: -90, latMax: 90 }
    expect(reliefTilesFor(world, 5).map(t => t.href)).toEqual([expect.stringMatching(/relief-4k\.webp$/)])
    // Alpy 5–15°E, 44–48°N: kolumna 8 (0–22,5°E), wiersze 1 i 2 (granica 45°N)
    const alps = reliefTilesFor({ lonMin: 5, lonMax: 15, latMin: 44, latMax: 48 }, 500)
    expect(alps.map(t => t.href.split('tiles/')[1])).toEqual(['2/1_8.webp', '2/2_8.webp'])
    const wrap = reliefTilesFor({ lonMin: 170, lonMax: 190, latMin: 0, latMax: 10 }, 500)
    expect(wrap.map(t => t.href.split('tiles/')[1])).toEqual(['2/3_15.webp', '2/3_0.webp'])
    expect(wrap[1].lonMin).toBe(180)
  })
})
