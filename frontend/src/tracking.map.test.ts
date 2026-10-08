// K3 — splitTrailSegments: trasa przecinająca antymerydian dzielona na segmenty,
// żeby polilinia nie rysowała fałszywej linii w poprzek całej mapy.
import { describe, expect, it } from 'vitest'
import { splitTrailSegments } from './pages/tracking/mapUtils'

describe('splitTrailSegments', () => {
  it('trasa bez przekroczenia antymerydianu — jeden segment', () => {
    const pts: [number, number][] = [[10, 100], [11, 105], [12, 110]]
    expect(splitTrailSegments(pts)).toEqual([pts])
  })

  it('skok +179 → -179 (przekroczenie 180°) — dzieli na dwa segmenty', () => {
    const pts: [number, number][] = [[10, 170], [11, 179], [12, -179], [13, -170]]
    const segments = splitTrailSegments(pts)
    expect(segments).toEqual([
      [[10, 170], [11, 179]],
      [[12, -179], [13, -170]],
    ])
  })

  it('pusta trasa — brak segmentów', () => {
    expect(splitTrailSegments([])).toEqual([])
  })

  it('pojedynczy punkt — jeden segment z jednym punktem', () => {
    expect(splitTrailSegments([[0, 0]])).toEqual([[[0, 0]]])
  })
})
