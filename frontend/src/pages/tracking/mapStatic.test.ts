import { describe, expect, it } from 'vitest'
import { px, py, supplierCoords } from './mapStatic'

// adresy w formacie importu LFA1: "ULICA, KOD MIASTO, KRAJ" (miasto wielkimi literami)
describe('supplierCoords', () => {
  it('dopasowuje chińskie miasto z adresu (case-insensitive)', () => {
    const r = supplierCoords('NO.5 XINXING RD, 322000 YIWU, CN', 'CN')
    expect(r).not.toBeNull()
    expect(r!.city).toBe('Yiwu')
    expect(r!.x).toBeCloseTo(px(120.07), 1)
    expect(r!.y).toBeCloseTo(py(29.31), 1)
  })

  it('dłuższa nazwa wygrywa (Zhongshan, nie fragment)', () => {
    expect(supplierCoords('IND ZONE, 528400 ZHONGSHAN, CN', 'CN')!.city).toBe('Zhongshan')
  })

  it('brak miasta w CN → centroid Chin (bez city)', () => {
    const r = supplierCoords('SOMEWHERE UNKNOWN 1, CN', 'CN')
    expect(r).not.toBeNull()
    expect(r!.city).toBeNull()
  })

  it('kraj spoza Chin → centroid kraju, miasto CN w adresie ignorowane', () => {
    const r = supplierCoords('SHANGHAI STR. 5, 20095 HAMBURG, DE', 'DE')
    expect(r).not.toBeNull()
    expect(r!.city).toBeNull()
    // centroid Niemiec — z grubsza środkowa Europa, nie Chiny
    expect(r!.x).toBeLessThan(px(30))
  })

  it('nieznany kraj → null (dostawca pomijany na mapie)', () => {
    expect(supplierCoords('ADDR', 'XX')).toBeNull()
  })
})
