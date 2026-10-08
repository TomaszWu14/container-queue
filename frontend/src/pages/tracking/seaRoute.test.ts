// Strażnik regresji: trasy statków na globusie NIE przecinają lądu. Każdą linię
// próbkujemy gęsto po wielkim okręgu i sprawdzamy dokładnym point-in-polygon na
// world-atlas land-50m (niezależnie od siatki routera). Tolerancje: pas brzegowy
// (dokładność 50m), okolica portu końcowego i osie kanałów/rzek, których Natural
// Earth nie ma jako wody (Suez, Panama, Łaba).
import { feature } from 'topojson-client'
import land50 from 'world-atlas/land-50m.json'
import { describe, expect, it } from 'vitest'
import { greatCirclePoints, type Vec3 } from './globeMath'
import { PASSAGES, seaPath, seaTrail, type LL } from './seaRoute'

const COAST_KM = 5       // pas brzegowy: dokładność linii brzegowej 50m (dziś przechodzi nawet przy 3)
const PORT_KM = 30       // podejście do nabrzeża (fix w porcie bywa „na lądzie")
const CANAL_KM = 6

type Ring = { pts: [number, number][]; x0: number; x1: number; y0: number; y1: number }
/* eslint-disable-next-line @typescript-eslint/no-explicit-any */
const topo = land50 as any
const rings: Ring[] = []
/* eslint-disable-next-line @typescript-eslint/no-explicit-any */
for (const f of feature(topo, topo.objects.land).features as any[]) {
  const polys: [number, number][][][] = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates
  for (const poly of polys) for (const ring of poly) {
    // ring przez antymerydian (Eurazja przez Czukotkę, Fidżi) → rozwinięte długości;
    // ring wokół bieguna (Antarktyda) domknięty przez biegun
    const pts: [number, number][] = []
    let off = 0
    for (const [lon, lat] of ring) {
      const prev = pts[pts.length - 1]
      if (prev && lon + off - prev[0] > 180) off -= 360
      else if (prev && lon + off - prev[0] < -180) off += 360
      pts.push([lon + off, lat])
    }
    const last = pts[pts.length - 1][0]
    if (Math.abs(last - pts[0][0]) > 180) {
      const pole = pts[0][1] < 0 ? -90 : 90
      pts.push([last, pole], [pts[0][0], pole], pts[0])
    }
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1])
    rings.push({ pts, x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) })
  }
}

const km = (a: LL, b: LL) => {
  const dLat = (b[0] - a[0]) * 111.2
  const dLon = (b[1] - a[1]) * 111.2 * Math.cos((a[0] + b[0]) / 2 * Math.PI / 180)
  return Math.hypot(dLat, dLon)
}
/* odległość punktu od odcinka (płasko w km, lokalnie wystarcza) */
function segKm(p: LL, a: LL, b: LL): number {
  const k = Math.cos(p[0] * Math.PI / 180)
  const ax = (a[1] - p[1]) * k, ay = a[0] - p[0], bx = (b[1] - p[1]) * k, by = b[0] - p[0]
  const dx = bx - ax, dy = by - ay
  const t = Math.max(0, Math.min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy || 1)))
  return Math.hypot(ax + t * dx, ay + t * dy) * 111.2
}
/** Czy punkt leży na lądzie głębiej niż COAST_KM od brzegu (parzystość po ringach). */
function deepLand(p: LL): boolean {
  const lat = p[0]
  let inside = false
  const near: [Ring, number][] = []
  for (const r of rings) for (const lon of [p[1], p[1] + 360, p[1] - 360]) {
    if (lon < r.x0 || lon > r.x1 || lat < r.y0 || lat > r.y1) continue
    near.push([r, lon])
    const q = r.pts
    for (let i = 0, j = q.length - 1; i < q.length; j = i++) {
      if ((q[i][1] > lat) !== (q[j][1] > lat) &&
          lon < (q[j][0] - q[i][0]) * (lat - q[i][1]) / (q[j][1] - q[i][1]) + q[i][0]) inside = !inside
    }
  }
  if (!inside) return false
  for (const [r, lon] of near) for (let i = 1; i < r.pts.length; i++) {
    const a: LL = [r.pts[i - 1][1], r.pts[i - 1][0]], b: LL = [r.pts[i][1], r.pts[i][0]]
    if (segKm([lat, lon], a, b) < COAST_KM) return false
  }
  return true
}
const nearCanal = (p: LL) => PASSAGES.some(c => c.canal &&
  c.pts.some((a, i) => i > 0 && segKm(p, c.pts[i - 1], a) < CANAL_KM))
const toLL = (v: Vec3): LL => {
  const lat = Math.asin(v[1] / Math.hypot(...v)) * 180 / Math.PI
  let lon = Math.atan2(v[2], -v[0]) * 180 / Math.PI - 180
  if (lon < -180) lon += 360
  return [lat, lon]
}

/** Punkty linii (co ~0.05°) leżące na lądzie poza tolerancjami. */
function landHits(line: LL[], ports: LL[]): LL[] {
  const bad: LL[] = []
  for (let i = 1; i < line.length; i++) {
    for (const v of greatCirclePoints(line[i - 1], line[i], 0.05)) {
      const p = toLL(v)
      if (ports.some(q => km(p, q) < PORT_KM) || nearCanal(p)) continue
      if (deepLand(p)) bad.push(p)
    }
  }
  return bad
}

const lengthKm = (line: LL[]) => line.slice(1).reduce((s, p, i) => s + km(line[i], p), 0)

const PORTS: Record<string, LL> = {
  Szanghaj: [30.62, 122.06],   // Yangshan
  Ningbo: [29.93, 121.87],
  Singapur: [1.26, 103.82],
  Gdansk: [54.39, 18.7],       // DCT
  Rotterdam: [51.95, 4.05],    // Maasvlakte
  Hamburg: [53.54, 9.93],
}

describe('seaPath — trasy port→port po wodzie', () => {
  it('checker lądu działa: goły wielki okrąg Szanghaj→Gdańsk trafia w ląd', () => {
    expect(landHits([PORTS.Szanghaj, PORTS.Gdansk], []).length).toBeGreaterThan(100)
  })

  const cases: [string, string, [number, number]][] = [
    // [od, do, widełki długości trasy km — łapią objazd Afryki / skrót przez Arktykę]
    ['Szanghaj', 'Gdansk', [18000, 23000]],
    ['Ningbo', 'Rotterdam', [17500, 22000]],
    ['Singapur', 'Hamburg', [14500, 18500]],
  ]
  for (const [from, to, [lo, hi]] of cases) {
    it(`${from} → ${to}: żaden punkt linii nie leży na lądzie`, () => {
      const line = seaPath(PORTS[from], PORTS[to])
      expect(line).not.toBeNull()
      expect(landHits(line!, [PORTS[from], PORTS[to]])).toEqual([])
      const L = lengthKm(line!)
      expect(L).toBeGreaterThan(lo)
      expect(L).toBeLessThan(hi)
    })
  }

  it('Szanghaj → Gdańsk idzie przez Suez (nie dookoła Afryki)', () => {
    const line = seaPath(PORTS.Szanghaj, PORTS.Gdansk)!
    expect(line.some(p => km(p, [30.6, 32.3]) < 60)).toBe(true)
  })
})

describe('seaTrail — ślad AIS z rzadkimi fixami', () => {
  it('fixy po obu stronach Półwyspu Malajskiego: linia obchodzi półwysep', () => {
    const trail: LL[] = [[6.2, 97.6], [5.5, 104.2]]   // M. Andamańskie → Zatoka Tajlandzka
    expect(landHits(trail, []).length).toBeGreaterThan(0)   // goły łuk przecina ląd
    const lines = seaTrail(trail)
    expect(lines).toHaveLength(1)
    expect(landHits(lines[0], [])).toEqual([])
  })

  it('fixy po obu stronach Jutlandii + kolejny fix na Bałtyku', () => {
    const trail: LL[] = [[56.2, 7.6], [56.6, 11.6], [55.0, 14.5]]
    expect(landHits(trail, []).length).toBeGreaterThan(0)
    const lines = seaTrail(trail)
    expect(lines).toHaveLength(1)
    expect(landHits(lines[0], [])).toEqual([])
    // linia przechodzi przez wszystkie fixy
    for (const p of trail) expect(lines[0].some(q => km(p, q) < 1)).toBe(true)
  })

  it('fixy na otwartym morzu łączy wprost (bez objazdów)', () => {
    const a: LL = [35.0, -40.0], b: LL = [36.0, -35.0]
    expect(seaPath(a, b)).toEqual([a, b])
  })
})
