// Routing po morzu dla śladów statków na globusie. Kolejne fixy AIS łączone gołym
// wielkim okręgiem potrafią „przejść" po lądzie (rzadkie pozycje, półwyspy) — tu
// każdy odcinek idzie po wodzie: siatka 0,25° z world-atlas land-50m (Natural
// Earth, domena publiczna) → A* → wygładzenie (string pulling) z testem widoczności
// po masce wody. Cieśniny/kanały węższe niż komórka (Suez, Bosfor, Sund…) to ręczne
// „przejścia" — polilinie po osi toru wodnego, wstawiane do trasy wprost.
// Bez zależności od three — testowalne w node (seaRoute.test.ts).
import { feature } from 'topojson-client'
import land50 from 'world-atlas/land-50m.json'
import { greatCirclePoints, type Vec3 } from './globeMath'

export type LL = [number, number]   // [lat, lon]

const STEP = 0.25                   // bok komórki w stopniach (~28 km na równiku)
const COLS = 360 / STEP, ROWS = 180 / STEP
// próbek na bok komórki: komórka jest wodą tylko, gdy WSZYSTKIE próbki są wodą —
// wtedy linia między środkami sąsiednich komórek wody nie ścina brzegu
const SUB = 3
const LOS_STEP = 0.05               // gęstość próbkowania testu widoczności (°)

/* Przejścia węższe niż komórka siatki (albo kanały, których Natural Earth nie ma
   jako wody) — polilinie [lat, lon] po osi toru wodnego, końce na otwartej wodzie. */
export const PASSAGES: { name: string; canal?: boolean; pts: LL[] }[] = [
  { name: 'Kanał Sueski + Zatoka Sueska', canal: true, pts: [
    [31.45, 32.36], [31.25, 32.31], [31.0, 32.32], [30.8, 32.32], [30.6, 32.29],
    [30.45, 32.35], [30.3, 32.45], [30.1, 32.56], [29.93, 32.57], [29.7, 32.63],
    [29.4, 32.75], [29.0, 32.95], [28.6, 33.2], [28.2, 33.5], [27.8, 33.8], [27.4, 34.15]] },
  { name: 'Kanał Panamski', canal: true, pts: [
    [9.5, -79.95], [9.3, -79.92], [9.2, -79.85], [9.1, -79.72], [9.0, -79.63],
    [8.9, -79.56], [8.8, -79.52], [8.6, -79.45]] },
  { name: 'Łaba (Hamburg)', canal: true, pts: [
    [53.54, 9.93], [53.56, 9.72], [53.64, 9.5], [53.78, 9.4], [53.88, 9.15],
    [53.9, 8.8], [53.98, 8.45], [54.05, 8.1]] },
  { name: 'Bab al-Mandab', pts: [[13.4, 42.8], [13.0, 43.1], [12.6, 43.3], [12.35, 43.5], [12.0, 43.9]] },
  { name: 'Gibraltar', pts: [[36.0, -6.6], [35.95, -5.8], [35.97, -5.5], [36.02, -5.2], [36.1, -4.6]] },
  { name: 'Cieśnina Kaletańska', pts: [[50.7, 0.9], [51.03, 1.5], [51.3, 1.85], [51.55, 2.2]] },
  { name: 'Sund', pts: [[56.4, 12.2], [56.04, 12.65], [55.85, 12.7], [55.6, 12.7], [55.4, 12.8], [55.2, 12.95], [55.0, 13.2]] },
  { name: 'Cieśnina Singapurska', pts: [
    [2.4, 101.4], [1.9, 102.4], [1.45, 103.2], [1.2, 103.55], [1.2, 103.8], [1.25, 104.05], [1.35, 104.5]] },
  { name: 'Dardanele + Bosfor', pts: [
    [39.9, 25.9], [40.05, 26.2], [40.2, 26.4], [40.4, 26.7], [40.6, 27.2], [40.8, 28.2],
    [40.95, 28.98], [41.05, 29.03], [41.12, 29.07], [41.2, 29.12], [41.35, 29.25]] },
  { name: 'Ormuz', pts: [[26.2, 55.5], [26.4, 55.95], [26.6, 56.45], [26.4, 56.85], [25.9, 57.2]] },
]
// Cieśnina Beringa zamurowana: bez tego A* puszcza Szanghaj→Europa Północną Drogą
// Morską (krótsza po kuli, ale kontenerowce płyną przez Suez)
const WALLS: { lat: [number, number]; lon: [number, number] }[] = [{ lat: [65.0, 67.0], lon: [-172, -166] }]
const OCEAN_SEED: LL = [0, -25]     // środek Atlantyku: główny akwen do flood-filla

const wrapLon = (lon: number) => ((lon + 180) % 360 + 360) % 360 - 180
const cellOf = (lat: number, lon: number) => {
  const r = Math.min(ROWS - 1, Math.max(0, Math.floor((90 - lat) / STEP)))
  const c = Math.min(COLS - 1, Math.floor((wrapLon(lon) + 180) / STEP))
  return r * COLS + c
}
const centerOf = (i: number): LL =>
  [90 - (Math.floor(i / COLS) + 0.5) * STEP, -180 + (i % COLS + 0.5) * STEP]
const toLL = (v: Vec3): LL => {
  const n = Math.hypot(v[0], v[1], v[2])
  const lat = Math.asin(Math.max(-1, Math.min(1, v[1] / n))) * 180 / Math.PI
  return [lat, wrapLon(Math.atan2(v[2], -v[0]) * 180 / Math.PI - 180)]
}

/* ---- maska lądu: rasteryzacja scanline poligonów land-50m (reguła parzystości) ---- */
function rasterLand(): Uint8Array {
  const FR = ROWS * SUB, FS = STEP / SUB
  const xs: number[][] = Array.from({ length: FR }, () => [])
  /* eslint-disable-next-line @typescript-eslint/no-explicit-any */
  const topo = land50 as any
  const fc = feature(topo, topo.objects.land)
  /* eslint-disable-next-line @typescript-eslint/no-explicit-any */
  const polys: number[][][][] = fc.features.flatMap((f: any) =>
    f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates)
  for (const poly of polys) for (const ring of poly) {
    // rozwinięcie długości: skok >180° to przejście przez antymerydian (Rosja, Fidżi)
    const u: LL[] = []
    let off = 0
    for (let k = 0; k < ring.length; k++) {
      const [lon, lat] = ring[k]
      if (k) {
        const d = lon + off - u[k - 1][0]
        if (d > 180) off -= 360; else if (d < -180) off += 360
      }
      u.push([lon + off, lat])
    }
    // ring okrążający biegun (Antarktyda) — domknięcie przez biegun
    const last = u[u.length - 1][0]
    if (Math.abs(last - u[0][0]) > 180) {
      const pole = u.reduce((s, p) => s + p[1], 0) < 0 ? -90 : 90
      u.push([last, pole], [u[0][0], pole])
    }
    for (let k = 0; k < u.length; k++) {
      const [x0, y0] = u[k], [x1, y1] = u[(k + 1) % u.length]
      if (y0 === y1) continue
      const lo = Math.min(y0, y1), hi = Math.max(y0, y1)
      const rA = Math.max(0, Math.ceil((90 - hi) / FS - 0.5))
      const rB = Math.min(FR - 1, Math.floor((90 - lo) / FS - 0.5))
      for (let r = rA; r <= rB; r++) {
        const y = 90 - (r + 0.5) * FS
        if (y >= lo && y < hi) xs[r].push(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
      }
    }
  }
  // komórka zgrubna = ląd, gdy którakolwiek próbka SUB×SUB jest lądem — spany
  // wiersza próbek od razu na komórki (bez pełnej siatki próbek)
  const land = new Uint8Array(ROWS * COLS)
  for (let r = 0; r < FR; r++) {
    const row = xs[r].sort((a, b) => a - b), base = Math.floor(r / SUB) * COLS
    for (let k = 0; k + 1 < row.length; k += 2) {
      const c0 = Math.ceil((row[k] + 180) / FS - 0.5), c1 = Math.floor((row[k + 1] + 180) / FS - 0.5)
      if (c1 < c0) continue
      for (let c = Math.floor(c0 / SUB); c <= Math.floor(c1 / SUB); c++) land[base + ((c % COLS) + COLS) % COLS] = 1
    }
  }
  return land
}

interface Grid {
  nav: Uint8Array          // 0 = ląd/odcięty akwen, 1 = woda, 2 = komórka przejścia
  passOf: Int16Array       // indeks przejścia (PASSAGES) dla komórek nav=2
  passT0: Float32Array     // zakres parametru polilinii przejścia w komórce
  passT1: Float32Array
}
let grid: Grid | null = null

/** Siatka nawigacyjna — budowana leniwie raz na sesję (~kilkaset ms). */
function getGrid(): Grid {
  if (grid) return grid
  const land = rasterLand()
  for (const w of WALLS) {
    for (let lat = w.lat[0]; lat <= w.lat[1]; lat += STEP / 2)
      for (let lon = w.lon[0]; lon <= w.lon[1]; lon += STEP / 2) land[cellOf(lat, lon)] = 1
  }
  const passOf = new Int16Array(ROWS * COLS).fill(-1)
  const passT0 = new Float32Array(ROWS * COLS), passT1 = new Float32Array(ROWS * COLS)
  PASSAGES.forEach((p, k) => {
    for (let s = 0; s + 1 < p.pts.length; s++) {
      const [a, b] = [p.pts[s], p.pts[s + 1]]
      const n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 0.01))
      for (let j = 0; j <= n; j++) {
        const t = s + j / n
        const i = cellOf(a[0] + (b[0] - a[0]) * j / n, a[1] + (b[1] - a[1]) * j / n)
        if (passOf[i] === -1) { passOf[i] = k; passT0[i] = t; passT1[i] = t; land[i] = 2 }
        else if (passOf[i] === k) { passT0[i] = Math.min(passT0[i], t); passT1[i] = Math.max(passT1[i], t) }
      }
    }
  })
  // flood fill z Atlantyku: jeziora i odcięte akweny (Kaspijskie) nie są żeglowne
  const nav = new Uint8Array(ROWS * COLS)
  const seed = cellOf(OCEAN_SEED[0], OCEAN_SEED[1])
  const stack = [seed]
  nav[seed] = 1
  while (stack.length) {
    const i = stack.pop()!
    const r = Math.floor(i / COLS), c = i % COLS
    for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
      const rr = r + dr
      if (rr < 0 || rr >= ROWS || (!dr && !dc)) continue
      const j = rr * COLS + (c + dc + COLS) % COLS
      if (nav[j] || land[j] === 1) continue
      nav[j] = land[j] === 2 ? 2 : 1
      stack.push(j)
    }
  }
  grid = { nav, passOf, passT0, passT1 }
  return grid
}

/** Czy wielki okrąg a→b idzie wyłącznie po wodzie (komórki końców pomijane —
    pozycja w porcie bywa „na lądzie" siatki). Komórki przejść liczą się jak ląd:
    przez cieśninę trasa idzie tylko wstawioną polilinią. */
function clearWater(g: Grid, a: LL, b: LL): boolean {
  const ca = cellOf(a[0], a[1]), cb = cellOf(b[0], b[1])
  for (const v of greatCirclePoints(a, b, LOS_STEP)) {
    const [lat, lon] = toLL(v)
    const c = cellOf(lat, lon)
    if (c !== ca && c !== cb && g.nav[c] !== 1) return false
  }
  return true
}

/** Najbliższa żeglowna komórka (kwadratowe pierścienie do ~10°) — dla fixów w porcie. */
function snap(g: Grid, p: LL): number {
  const i0 = cellOf(p[0], p[1])
  if (g.nav[i0]) return i0
  const r0 = Math.floor(i0 / COLS), c0 = i0 % COLS
  for (let k = 1; k <= 40; k++) {
    let best = -1, bestD = Infinity
    for (let dr = -k; dr <= k; dr++) for (let dc = -k; dc <= k; dc++) {
      if (Math.max(Math.abs(dr), Math.abs(dc)) !== k) continue
      const r = r0 + dr
      if (r < 0 || r >= ROWS) continue
      const j = r * COLS + (c0 + dc + COLS) % COLS
      if (!g.nav[j]) continue
      const [lat, lon] = centerOf(j)
      const d = Math.hypot(lat - p[0], (lon - p[1]) * Math.cos(p[0] * Math.PI / 180))
      if (d < bestD) { bestD = d; best = j }
    }
    if (best >= 0) return best
  }
  return -1
}

/* ---- A* po siatce (8 sąsiadów, zawinięcie po długości) ---- */
const D2R = Math.PI / 180
let gScore: Float32Array, parent: Int32Array, seen: Uint32Array, done: Uint32Array
let gen = 0
const MAX_EXPAND = 1_500_000

function astar(g: Grid, s: number, t: number): number[] | null {
  if (!gScore) {
    gScore = new Float32Array(ROWS * COLS); parent = new Int32Array(ROWS * COLS)
    seen = new Uint32Array(ROWS * COLS); done = new Uint32Array(ROWS * COLS)
  }
  gen++
  const [tLat, tLon] = centerOf(t)
  const sinT = Math.sin(tLat * D2R), cosT = Math.cos(tLat * D2R)
  const h = (i: number) => {
    const [lat, lon] = centerOf(i)
    const c = Math.sin(lat * D2R) * sinT + Math.cos(lat * D2R) * cosT * Math.cos((lon - tLon) * D2R)
    return Math.acos(Math.max(-1, Math.min(1, c))) / D2R
  }
  // kopiec binarny (f, indeks) na zwykłych tablicach; duplikaty zamiast decrease-key
  const hf: number[] = [], hi: number[] = []
  const push = (f: number, i: number) => {
    let k = hf.length
    hf.push(f); hi.push(i)
    while (k > 0) {
      const p = (k - 1) >> 1
      if (hf[p] <= hf[k]) break
      ;[hf[p], hf[k]] = [hf[k], hf[p]]; [hi[p], hi[k]] = [hi[k], hi[p]]
      k = p
    }
  }
  const pop = () => {
    const top = hi[0]
    const lf = hf.pop()!, li = hi.pop()!
    if (hf.length) {
      hf[0] = lf; hi[0] = li
      let k = 0
      for (;;) {
        const l = 2 * k + 1, r = l + 1
        let m = k
        if (l < hf.length && hf[l] < hf[m]) m = l
        if (r < hf.length && hf[r] < hf[m]) m = r
        if (m === k) break
        ;[hf[m], hf[k]] = [hf[k], hf[m]]; [hi[m], hi[k]] = [hi[k], hi[m]]
        k = m
      }
    }
    return top
  }
  gScore[s] = 0; parent[s] = -1; seen[s] = gen
  push(h(s), s)
  let expanded = 0
  while (hf.length) {
    const i = pop()
    if (done[i] === gen) continue
    done[i] = gen
    if (i === t) {
      const path: number[] = []
      for (let k = t; k !== -1; k = parent[k]) path.push(k)
      return path.reverse()
    }
    if (++expanded > MAX_EXPAND) return null
    const r = Math.floor(i / COLS), c = i % COLS
    const cosLat = Math.cos((90 - (r + 0.5) * STEP) * D2R)
    for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
      const rr = r + dr
      if (rr < 0 || rr >= ROWS || (!dr && !dc)) continue
      const j = rr * COLS + (c + dc + COLS) % COLS
      if (!g.nav[j] || done[j] === gen) continue
      // po skosie tylko, gdy nie przeciskamy się między dwiema komórkami lądu
      if (dr && dc && !g.nav[rr * COLS + c] && !g.nav[r * COLS + (c + dc + COLS) % COLS]) continue
      const ng = gScore[i] + STEP * Math.hypot(dr, dc * cosLat)
      if (seen[j] === gen && ng >= gScore[j]) continue
      seen[j] = gen; gScore[j] = ng; parent[j] = i
      push(ng + h(j), j)
    }
  }
  return null
}

/* fragment polilinii przejścia między parametrami t0→t1 (t = indeks odcinka + ułamek) */
function passagePiece(pts: LL[], t0: number, t1: number): LL[] {
  const at = (t: number): LL => {
    const s = Math.min(pts.length - 2, Math.floor(t)), f = t - s
    return [pts[s][0] + (pts[s + 1][0] - pts[s][0]) * f, pts[s][1] + (pts[s + 1][1] - pts[s][1]) * f]
  }
  const out: LL[] = [at(t0)]
  if (t1 >= t0) { for (let v = Math.floor(t0) + 1; v < t1; v++) out.push(pts[v]) }
  else { for (let v = Math.ceil(t0) - 1; v > t1; v--) out.push(pts[v]) }
  out.push(at(t1))
  return out
}

/* parametr t najbliższego punktu polilinii (próbkowanie co 1/20 odcinka) */
function nearestT(pts: LL[], p: LL): number {
  let best = 0, bestD = Infinity
  for (let t = 0; t <= pts.length - 1; t += 0.05) {
    const s = Math.min(pts.length - 2, Math.floor(t)), f = t - s
    const d = Math.hypot(pts[s][0] + (pts[s + 1][0] - pts[s][0]) * f - p[0],
      pts[s][1] + (pts[s + 1][1] - pts[s][1]) * f - p[1])
    if (d < bestD) { bestD = d; best = t }
  }
  return best
}

/** Trasa po wodzie z a do b jako punkty zwrotne [lat, lon] (końce włącznie) —
    kolejne punkty łączy wielki okrąg. null = brak drogi po wodzie (akwen odcięty). */
export function seaPath(a: LL, b: LL): LL[] | null {
  const g = getGrid()
  if (clearWater(g, a, b)) return [a, b]
  const s = snap(g, a), t = snap(g, b)
  if (s < 0 || t < 0) return null
  const cells = s === t ? [s] : astar(g, s, t)
  if (!cells) return null
  // punkty zwrotne: środki komórek wody + polilinie przejść (fixed — nie wygładzamy)
  const wps: LL[] = [a], fixed: boolean[] = [true]
  for (let k = 0; k < cells.length; k++) {
    const i = cells[k]
    if (g.nav[i] !== 2) { wps.push(centerOf(i)); fixed.push(false); continue }
    let e = k
    while (e + 1 < cells.length && g.nav[cells[e + 1]] === 2 && g.passOf[cells[e + 1]] === g.passOf[i]) e++
    const last = cells[e]
    const pts = PASSAGES[g.passOf[i]].pts
    const fwd = g.passT0[last] >= g.passT0[i]
    // początek/koniec trasy wewnątrz przejścia (port nad kanałem) → od/do rzutu punktu
    const tIn = k === 0 ? nearestT(pts, a) : fwd ? g.passT0[i] : g.passT1[i]
    const tOut = e === cells.length - 1 ? nearestT(pts, b) : fwd ? g.passT1[last] : g.passT0[last]
    for (const p of passagePiece(pts, tIn, tOut)) { wps.push(p); fixed.push(true) }
    k = e
  }
  wps.push(b); fixed.push(true)
  // string pulling: z punktu i sięgamy najdalej, dokąd widać wodę; fixed zostają zawsze
  const out: LL[] = [wps[0]]
  let i = 0
  while (i < wps.length - 1) {
    let j = i + 1
    while (j + 1 < wps.length && !fixed[j] && clearWater(g, wps[i], wps[j + 1])) j++
    const q = wps[j], prev = out[out.length - 1]
    if (q[0] !== prev[0] || q[1] !== prev[1]) out.push(q)
    i = j
  }
  return out
}

const cache = new Map<string, LL[] | null>()

/** Ślad statku (kolejne fixy) → ciągłe polilinie po wodzie. Odcinek bez drogi po
    wodzie przerywa linię (lepsza przerwa niż kreska przez ląd). */
export function seaTrail(points: LL[]): LL[][] {
  const lines: LL[][] = []
  let cur: LL[] = []
  for (let k = 1; k < points.length; k++) {
    const key = `${points[k - 1]}|${points[k]}`
    let p = cache.get(key)
    if (p === undefined) {
      p = seaPath(points[k - 1], points[k])
      if (cache.size > 5000) cache.clear()   // ponytail: prosty limit zamiast LRU
      cache.set(key, p)
    }
    if (!p) { if (cur.length > 1) lines.push(cur); cur = []; continue }
    cur.push(...(cur.length ? p.slice(1) : p))
  }
  if (cur.length > 1) lines.push(cur)
  return lines
}
