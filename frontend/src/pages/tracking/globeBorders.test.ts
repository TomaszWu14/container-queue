import { describe, expect, it } from 'vitest'
import { borderSegments, countryBorderLines } from './globeBorders'

const radius = (a: Float32Array, i: number) => Math.hypot(a[i], a[i + 1], a[i + 2])

describe('borderSegments', () => {
  it('długi odcinek po równoleżniku dzielony co ≤1° (cięciwa nie wpada pod kulę)', () => {
    const pos = borderSegments([[[-120, 49], [-95, 49]]], 100)
    expect(pos.length / 6).toBe(25)                     // 25 odcinków po 1°
    for (let i = 0; i < pos.length; i += 3) expect(radius(pos, i)).toBeCloseTo(100, 3)
    // y stałe = szerokość 49° się nie zmienia
    expect(pos[1]).toBeCloseTo(pos[pos.length - 2], 4)
  })
  it('skok przez antymerydian jest pomijany (bez kreski przez cały glob)', () => {
    expect(borderSegments([[[179.5, -16], [-179.5, -16]]], 100).length).toBe(0)
  })
})

describe('countryBorderLines', () => {
  it('50m: granice lądowe (bez wybrzeży) w ~20 tys. punktów, współrzędne lon/lat', () => {
    const lines = countryBorderLines()
    expect(lines.length).toBeGreaterThan(150)
    expect(lines.reduce((n, l) => n + l.length, 0)).toBeGreaterThan(15000)   // 110m miało ~4×mniej
    const [lon, lat] = lines[0][0]
    expect(Math.abs(lon)).toBeLessThanOrEqual(180)
    expect(Math.abs(lat)).toBeLessThanOrEqual(90)
  })
})
