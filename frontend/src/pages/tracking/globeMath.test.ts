// Matematyka i helpery globusa: wielki okrąg (trasa/replay), eksport PNG, replay.
import { describe, expect, it } from 'vitest'
import {
  canExportCanvas, declutterLabels, exportFilename, greatCirclePoints, labelBox, latLonToVec3, replayPointAt,
} from './globeMath'

describe('declutterLabels (odkolizjonowanie etykiet globusa)', () => {
  it('ukrywa nachodzącą etykietę o niższym priorytecie, zostawia wyższy', () => {
    const hide = declutterLabels([
      { cx: 100, cy: 100, hw: 20, hh: 6, pri: 9 },   // niższy pri
      { cx: 110, cy: 102, hw: 20, hh: 6, pri: 12 },  // wyższy pri, nachodzi
    ])
    expect(hide.has(1)).toBe(false)   // wyższy priorytet zostaje
    expect(hide.has(0)).toBe(true)    // niższy, kolidujący — ukryty
  })
  it('nie ukrywa etykiet, które się nie stykają', () => {
    const hide = declutterLabels([
      { cx: 0, cy: 0, hw: 10, hh: 5, pri: 5 },
      { cx: 100, cy: 100, hw: 10, hh: 5, pri: 5 },
    ])
    expect(hide.size).toBe(0)
  })
  it('B12: widzi nakładanie etykiet rysowanych NAD punktem (center.y < 0)', () => {
    // punkty 20 px w pionie (> 2·hh = 16, więc prostokąty wokół samych punktów się nie stykają),
    // ale etykieta dolnego (centerY -0.8) wisi wyżej niż górnego (-0.35) i wchodzi na nią
    expect(declutterLabels([
      { cx: 100, cy: 100, hw: 30, hh: 8, pri: 12 }, { cx: 100, cy: 120, hw: 30, hh: 8, pri: 9 },
    ]).size).toBe(0)
    const top = labelBox(100, 100, 30, 8, -0.35, 12)
    const low = labelBox(100, 120, 30, 8, -0.8, 9)
    expect(declutterLabels([top, low]).has(1)).toBe(true)
  })
})

describe('labelBox (prostokąt kolizji sprite\'a z przesuniętym center)', () => {
  it('center.y 0.5 = prostokąt wokół punktu; niższy center.y przesuwa go w górę ekranu', () => {
    expect(labelBox(50, 200, 20, 10, 0.5, 1)).toEqual({ cx: 50, cy: 200, hw: 20, hh: 10, pri: 1 })
    // center.y -0.35 → środek tekstu 0.85 wysokości (2·hh = 20 px) nad punktem = 17 px
    expect(labelBox(50, 200, 20, 10, -0.35, 1).cy).toBeCloseTo(183)
  })
})

describe('greatCirclePoints (próbkowanie trasy / trail na kuli)', () => {
  it('zaczyna i kończy w punktach wejściowych, punkty leżą na sferze', () => {
    const pts = greatCirclePoints([1.29, 103.85], [54.4, 18.66], 2, 100)
    const start = latLonToVec3(1.29, 103.85, 100)
    const end = latLonToVec3(54.4, 18.66, 100)
    for (let i = 0; i < 3; i++) {
      expect(pts[0][i]).toBeCloseTo(start[i], 6)
      expect(pts[pts.length - 1][i]).toBeCloseTo(end[i], 6)
    }
    for (const p of pts) {
      expect(Math.hypot(p[0], p[1], p[2])).toBeCloseTo(100, 6)
    }
    expect(pts.length).toBeGreaterThan(10)   // segmentacja co ~2°
  })

  it('punkty pokrywające się → tylko końce (bez NaN)', () => {
    const pts = greatCirclePoints([10, 20], [10, 20], 2, 1)
    expect(pts).toHaveLength(2)
    expect(pts.flat().every(Number.isFinite)).toBe(true)
  })
})

describe('eksport PNG (feature-detect + nazwa pliku)', () => {
  it('canExportCanvas wykrywa toBlob', () => {
    expect(canExportCanvas({ toBlob: () => {} })).toBe(true)
    expect(canExportCanvas({})).toBe(false)
    expect(canExportCanvas(null)).toBe(false)
  })

  it('exportFilename: kolejka-globus-YYYY-MM-DD.png z zerami wiodącymi', () => {
    expect(exportFilename(new Date(2026, 8, 18))).toBe('kolejka-globus-2026-09-18.png')
    expect(exportFilename(new Date(2026, 0, 5))).toBe('kolejka-globus-2026-01-05.png')
  })
})

describe('replayPointAt (stan replayu wspólny 2D/3D)', () => {
  const trail: [number, number][] = [[1, 1], [2, 2], [3, 3]]

  it('zwraca punkt pod indeksem', () => {
    expect(replayPointAt(trail, 1)).toEqual([2, 2])
  })

  it('clampuje indeks poza zakresem (trail skrócony po odświeżeniu)', () => {
    expect(replayPointAt(trail, 99)).toEqual([3, 3])
    expect(replayPointAt(trail, -5)).toEqual([1, 1])
  })

  it('pusty trail → null (replay wyłączony)', () => {
    expect(replayPointAt([], 0)).toBeNull()
  })
})
