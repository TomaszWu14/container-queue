// Czysta matematyka globusa 3D (bez three.js — testowalna w node/jsdom):
// konwersja lat/lon → wektor 3D, wielki okrąg (slerp), culling horyzontu,
// pozycja słońca (terminator dzień/noc), rozrzedzanie etykiet.

export type Vec3 = [number, number, number]

/** lat/lon → punkt na sferze o promieniu r. Konwencja zgodna z UV
    THREE.SphereGeometry dla tekstury equirectangular (u = (lon+180)/360). */
export function latLonToVec3(lat: number, lon: number, r = 1): Vec3 {
  const phi = (90 - lat) * Math.PI / 180
  const theta = (lon + 180) * Math.PI / 180
  return [
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  ]
}

const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const len = (a: Vec3) => Math.hypot(a[0], a[1], a[2])

/** Wielki okrąg między dwoma punktami (lat,lon) — slerp segmentowany co ~stepDeg,
    żeby polilinia leżała na powierzchni sfery. Antymerydian nie wymaga specjalnego
    traktowania: interpolujemy wektory 3D, nie długości geograficzne. */
export function greatCirclePoints(
  a: [number, number], b: [number, number], stepDeg = 2, r = 1,
): Vec3[] {
  const va = latLonToVec3(a[0], a[1], 1)
  const vb = latLonToVec3(b[0], b[1], 1)
  const d = Math.min(1, Math.max(-1, dot(va, vb)))
  const ang = Math.acos(d)
  const sinAng = Math.sin(ang)
  // punkty pokrywające się lub antypodalne (nieskończenie wiele wielkich okręgów)
  // → tylko końce; trasa AIS nigdy nie skacze o 180° w jednym kroku
  if (ang < 1e-6 || sinAng < 1e-6) return [va.map(v => v * r) as Vec3, vb.map(v => v * r) as Vec3]
  const n = Math.max(1, Math.ceil(ang / (stepDeg * Math.PI / 180)))
  const out: Vec3[] = []
  for (let i = 0; i <= n; i++) {
    const t = i / n
    const ka = Math.sin((1 - t) * ang) / sinAng
    const kb = Math.sin(t * ang) / sinAng
    out.push([
      (ka * va[0] + kb * vb[0]) * r,
      (ka * va[1] + kb * vb[1]) * r,
      (ka * va[2] + kb * vb[2]) * r,
    ])
  }
  return out
}

/** Czy punkt na sferze (promień r) jest przed horyzontem kuli widzianej z kamery
    w pozycji cam? Widoczny ⇔ cos kąta(punkt, kamera) > r/|cam|. */
export function isFrontFacing(p: Vec3, cam: Vec3, r = 1): boolean {
  const dCam = len(cam)
  if (dCam <= r) return true
  const pn = len(p)
  if (pn === 0) return false
  return dot(p, cam) / (pn * dCam) > r / dCam - 0.01
}

/** Kierunek do słońca (wektor jednostkowy) wg realnej daty UTC — punkt podsłoneczny:
    deklinacja (przybliżenie sinusoidalne) + kąt godzinny (południe słoneczne). */
export function sunDirection(date: Date): Vec3 {
  const start = Date.UTC(date.getUTCFullYear(), 0, 0)
  const day = (date.getTime() - start) / 86400000
  const decl = 23.44 * Math.sin(2 * Math.PI * (day - 81) / 365)
  const utcH = date.getUTCHours() + date.getUTCMinutes() / 60 + date.getUTCSeconds() / 3600
  const lon = (12 - utcH) * 15   // słońce w zenicie tam, gdzie lokalne południe
  return latLonToVec3(decl, lon, 1)
}

/** Proste rozrzedzenie etykiet: zachowaj punkt tylko, gdy żaden już zachowany nie
    leży bliżej niż minDeg stopni (przybliżenie kątowe po lat/lon). Zwraca indeksy. */
// ponytail: O(n²) — przy <1000 portów wystarcza; siatka przestrzenna gdyby urosło
export function thinByDistance(pts: { lat: number; lon: number }[], minDeg: number): number[] {
  const kept: number[] = []
  for (let i = 0; i < pts.length; i++) {
    let ok = true
    for (const j of kept) {
      const dLat = pts[i].lat - pts[j].lat
      let dLon = Math.abs(pts[i].lon - pts[j].lon)
      if (dLon > 180) dLon = 360 - dLon
      if (Math.hypot(dLat, dLon * Math.cos(pts[i].lat * Math.PI / 180)) < minDeg) { ok = false; break }
    }
    if (ok) kept.push(i)
  }
  return kept
}

/** Etykieta w screen-space: środek (px), połowy szerokości/wysokości, priorytet. */
export interface LabelBox { cx: number; cy: number; hw: number; hh: number; pri: number }

/** Prostokąt kolizji sprite'a zaczepionego w (cx, cy) z `center.y` = centerY: sprite
 * rysuje się (0.5 − centerY)·wysokość nad punktem (oś y ekranu rośnie w dół). */
export function labelBox(
  cx: number, cy: number, hw: number, hh: number, centerY: number, pri: number,
): LabelBox {
  return { cx, cy: cy - (0.5 - centerY) * 2 * hh, hw, hh, pri }
}

/** Odkolizjonowanie etykiet: zachłannie od najwyższego priorytetu, ukryj każdą,
 * której prostokąt nachodzi na już zachowaną (AABB). Remis priorytetu → wcześniejsza
 * na wejściu wygrywa (podawaj bliższe kamerze pierwsze). Zwraca indeksy DO UKRYCIA. */
export function declutterLabels(boxes: LabelBox[]): Set<number> {
  const order = boxes.map((_, i) => i).sort((a, b) => boxes[b].pri - boxes[a].pri || a - b)
  const kept: number[] = []
  const hide = new Set<number>()
  for (const i of order) {
    const a = boxes[i]
    const clash = kept.some(j => {
      const b = boxes[j]
      return Math.abs(a.cx - b.cx) < a.hw + b.hw && Math.abs(a.cy - b.cy) < a.hh + b.hh
    })
    if (clash) hide.add(i); else kept.push(i)
  }
  return hide
}

/* --- eksport PNG globusa --- */

/** Feature-detect: czy canvas umie toBlob (stare WebViews go nie mają). */
export function canExportCanvas(canvas: { toBlob?: unknown } | null | undefined): boolean {
  return typeof canvas?.toBlob === 'function'
}

/** Nazwa pliku eksportu: kolejka-globus-YYYY-MM-DD.png (data lokalna). */
export function exportFilename(date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `kolejka-globus-${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}.png`
}

/** Pobranie PNG z canvasu globusa (wołać tuż po synchronicznym renderze — bez
    preserveDrawingBuffer bufor po ostatnim rAF bywa wyczyszczony i PNG wychodzi czarny). */
export function downloadCanvasPng(canvas: HTMLCanvasElement): void {
  if (!canExportCanvas(canvas)) return
  canvas.toBlob(blob => {
    if (!blob) return
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = exportFilename()
    a.click()
    URL.revokeObjectURL(a.href)
  })
}

/* --- replay rejsu: wspólny stan 2D/3D --- */

/** Punkt trailu pod suwakiem replay — clamp na koniec, gdy trail się skrócił
    (odświeżenie danych w trakcie przewijania). */
export function replayPointAt(
  trail: [number, number][], index: number,
): [number, number] | null {
  if (!trail.length) return null
  return trail[Math.min(Math.max(0, index), trail.length - 1)]
}

/* --- tryb mapy 2D/3D — zapamiętany w localStorage, domyślnie 3D --- */
export type MapMode = '2d' | '3d'
const MODE_KEY = 'trackingMapMode'
export function readMapMode(): MapMode {
  try { return localStorage.getItem(MODE_KEY) === '2d' ? '2d' : '3d' } catch { return '3d' }
}
export function storeMapMode(mode: MapMode): void {
  try { localStorage.setItem(MODE_KEY, mode) } catch { /* prywatny tryb / quota */ }
}

// Presety widoku globu (makieta „Globus Kolejka"): skok kamery nad region.
// distMul = mnożnik promienia globu (mniej = bliżej). Suez najbliżej, Cały glob najdalej.
export type ViewPreset = { lat: number; lon: number; distMul: number }
export const VIEW_PRESETS: Record<'europe' | 'asia' | 'suez' | 'globe', ViewPreset> = {
  europe: { lat: 50, lon: 12, distMul: 1.7 },
  asia:   { lat: 28, lon: 112, distMul: 1.95 },
  suez:   { lat: 29, lon: 33, distMul: 1.4 },
  globe:  { lat: 20, lon: 45, distMul: 3.1 },
}
