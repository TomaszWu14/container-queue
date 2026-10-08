// Mapa wektorowa przy zbliżeniu (decyzja usera 2026-10-01): zdjęcie Blue Marble tylko z daleka,
// z bliska płynne przejście w czystą mapę wektorową (ląd, morze, wybrzeże, granice) — ostra
// przy każdym zoomie, offline (world-atlas 50m z node_modules, zero nowych plików/zapytań).
// Tu czysta matematyka progu + ścieżki 2D w projekcji świata 1000×500 — wspólne dla mapy 2D
// (FlatMap) i globusa (globeVector). Bez three.js — testowalne w node.
import { mesh } from 'topojson-client'
import atlas from 'world-atlas/countries-50m.json'
import { WORLD_H, WORLD_W } from '../../worldmap'

const DEG = Math.PI / 180
/** Natywna gęstość źródła: Blue Marble 21600 px na 360° = 60 px/°. */
export const NATIVE_PX_PER_DEG = 21600 / 360
// Przejście zdjęcie → wektor w skali „px ekranu (fizyczne) na teksel źródła":
// do 1,0 (teksel = 1 px — zdjęcie jeszcze w natywnej ostrości) tylko zdjęcie, od 2,0
// (teksel rozciągnięty na 2 px — widocznie rozmazany) tylko wektor. Wcześniej okno 0,5→1
// włączało wektor już na widoku całej Europy, gdzie zdjęcie wyglądało dobrze (feedback 2026-10-01).
// Interpolacja logarytmiczna (zoom jest mnożnikowy) + smoothstep — bez twardego przeskoku.
export const FADE_FROM = 1
export const FADE_TO = 2

/** Udział warstwy wektorowej 0..1 dla gęstości ekranu ppd [px fizyczne / °] względem natywnej
    gęstości tekstury pod spodem (domyślnie zdjęcie Blue Marble). */
export function vectorMix(ppd: number, native = NATIVE_PX_PER_DEG): number {
  const r = ppd / native
  if (!(r > 0)) return 0
  const t = Math.min(1, Math.max(0, Math.log2(r / FADE_FROM) / Math.log2(FADE_TO / FADE_FROM)))
  return t * t * (3 - 2 * t)
}

/** Mapa 2D: kadr szerokości viewW (jednostki świata) na ekranie screenW px CSS przy dpr. */
export const flatPxPerDeg = (viewW: number, screenW: number, dpr = 1) =>
  viewW > 0 ? screenW * dpr / (viewW / WORLD_W * 360) : 0

/** Globus: gęstość w punkcie pod kamerą (odległość dist od środka kuli R, fov pionowy [°],
    hPx = wysokość bufora rysowania w px fizycznych). */
export const globePxPerDeg = (dist: number, R: number, fovDeg: number, hPx: number) =>
  (hPx / 2) / Math.tan(fovDeg * DEG / 2) * R / Math.max(1e-6, dist - R) * DEG

type LonLat = [number, number]
const px = (lon: number) => (lon + 180) / 360 * WORLD_W
const py = (lat: number) => (90 - lat) / 180 * WORLD_H

/** Polilinie lon/lat → path SVG w jednostkach świata; skok przez antymerydian = nowy odcinek
    (inaczej linia w poprzek całej mapy). */
export function linesToPath(lines: LonLat[][]): string {
  let d = ''
  for (const line of lines) {
    line.forEach(([lon, lat], i) => {
      const jump = i === 0 || Math.abs(lon - line[i - 1][0]) > 180
      d += `${jump ? 'M' : 'L'}${px(lon).toFixed(2)},${py(lat).toFixed(2)}`
    })
  }
  return d
}

let paths: { coast: string; borders: string } | null = null
/** Wybrzeże (krawędzie bez sąsiada) i granice lądowe (wspólne krawędzie) — każda raz, liczone raz. */
export function vectorPaths(): { coast: string; borders: string } {
  if (!paths) {
    /* eslint-disable-next-line @typescript-eslint/no-explicit-any */
    const topo = atlas as any
    const lines = (f: (a: unknown, b: unknown) => boolean) =>
      mesh(topo, topo.objects.countries, f).coordinates as LonLat[][]
    paths = { coast: linesToPath(lines((a, b) => a === b)), borders: linesToPath(lines((a, b) => a !== b)) }
  }
  return paths
}

/** Odcień państwa w trybie wektorowym → nazwa tokena --map-vec-tint-1..6. Tokeny mają wyłącznie
    ciepłe/neutralne barwy (nigdy niebieskie — ląd nie może zlewać się z morzem). Kody ISO numeric
    to często wielokrotności 4 (DE 276, NL 528), stąd /4 — inaczej sąsiedzi dostawali ten sam odcień. */
export const VEC_TINTS = 6
export const vecTintVar = (c: { id: number; name: string }) =>
  `--map-vec-tint-${(Number.isFinite(c.id) ? Math.floor(Math.abs(c.id) / 4) : c.name.length) % VEC_TINTS + 1}`
/** Podświetlenia krajów na trasie (HL) w trybie wektorowym — też tylko ciepłe tokeny. */
export const VEC_HL_VAR = { dest: '--map-vec-hl-dest', origin: '--map-vec-hl-origin', transit: '--map-vec-hl-transit' } as const

export interface Region { lonMin: number; lonMax: number; latMin: number; latMax: number }

/** Prostokąt lat/lon pokrywający czaszę (środek lat/lon, promień capDeg) z zapasem `margin`;
    długość może wyjść poza ±180 (łata sfery zawija się sama), szerokość przycięta do biegunów. */
export function regionFor(lat: number, lon: number, capDeg: number, margin = 1.2): Region {
  const c = capDeg * margin + 0.5
  const latMin = Math.max(-90, lat - c), latMax = Math.min(90, lat + c)
  const maxAbs = Math.max(Math.abs(latMin), Math.abs(latMax))
  const half = maxAbs >= 89 ? 180 : Math.min(180, c / Math.cos(maxAbs * DEG))
  return { lonMin: lon - half, lonMax: lon + half, latMin, latMax }
}

/** Czy narysowany region `a` obejmuje potrzebny `b` (z dokładnością do przesunięcia o 360°). */
export function covers(a: Region, b: Region): boolean {
  if (b.latMin < a.latMin || b.latMax > a.latMax) return false
  if (a.lonMax - a.lonMin >= 360) return true
  return [-360, 0, 360].some(k => b.lonMin + k >= a.lonMin && b.lonMax + k <= a.lonMax)
}

/** Rozmiar canvasa regionu [px] dla gęstości ppd, ograniczony do maxSide (proporcjonalnie). */
export function regionCanvasSize(r: Region, ppd: number, maxSide: number): { w: number; h: number } {
  const latC = (r.latMin + r.latMax) / 2
  const w0 = (r.lonMax - r.lonMin) * ppd * Math.max(0.2, Math.cos(latC * DEG))
  const h0 = (r.latMax - r.latMin) * ppd
  const k = Math.min(1, maxSide / Math.max(w0, h0))
  return { w: Math.max(2, Math.round(w0 * k)), h: Math.max(2, Math.round(h0 * k)) }
}
