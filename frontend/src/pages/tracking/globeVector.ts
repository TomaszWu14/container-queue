// Globus przy zbliżeniu: mapa wektorowa zamiast rozmazanego zdjęcia (vectorMap.ts — próg).
// Region pod kamerą rysujemy do canvasa w rozdzielczości ekranu (ląd, morze, kolory państw,
// wybrzeże, granice — linie 1 px fizyczny) i nakładamy jako łatę sfery jak kafelki LOD
// (equirectangular UV). Przerysowanie dopiero po zatrzymaniu kamery (debounce) i tylko gdy
// kadr wyjdzie poza narysowany region albo zmieni się gęstość — w ruchu zostaje stara łata.
// Kolory z tokenów CSS (--map-vec-*), czytane przy każdym rysowaniu → oba motywy.
import type { Camera, PerspectiveCamera, Scene, WebGLRenderer } from 'three'
import { WORLD_H, WORLD_W } from '../../worldmap'
import { capRadiusDeg } from './globeTiles'
import { COUNTRIES, HL, LAND_PATH } from './mapStatic'
import { loadReliefFor, type LoadedRelief } from './reliefTiles'
import {
  covers, globePxPerDeg, regionCanvasSize, regionFor, VEC_HL_VAR, vecTintVar, vectorMix, vectorPaths,
  type Region,
} from './vectorMap'

type Three = typeof import('three')
const DEG = Math.PI / 180
const REDRAW_MS = 140
/** Szerokość tekstury terenu całej kuli (globeScene.addEarth, tryb bez zdjęcia). */
export const TERRAIN_TEX_W = 8192

// Path2D parsujemy raz na sesję (50m ≈ setki tysięcy współrzędnych)
let p2d: { land: Path2D; coast: Path2D; borders: Path2D; countries: { c: typeof COUNTRIES[number]; p: Path2D }[] } | null = null
const parsed = () => {
  if (!p2d) {
    const v = vectorPaths()
    p2d = { land: new Path2D(LAND_PATH), coast: new Path2D(v.coast), borders: new Path2D(v.borders),
      countries: COUNTRIES.map(c => ({ c, p: new Path2D(c.path) })) }
  }
  return p2d
}

const token = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback

export interface VectorOpts { countryColors: boolean; highlights: boolean; satellite?: boolean }

/** Region (lon/lat) → canvas w×h: morze, ląd, kolory państw/HL, rzeźba terenu (hard-light),
    granice, wybrzeże. lineScale > 1 dla tekstury całej kuli (oglądanej w pomniejszeniu). */
export function paintVectorRegion(canvas: HTMLCanvasElement, r: Region, w: number, h: number,
                                  opts: VectorOpts, relief: LoadedRelief = [], lineScale = 1) {
  canvas.width = w; canvas.height = h
  const ctx = canvas.getContext('2d')!
  const P = parsed()
  ctx.fillStyle = token('--map-vec-sea', 'steelblue')
  ctx.fillRect(0, 0, w, h)
  // jednostki świata → px canvasa; geometrię przekształcamy (addPath z macierzą), nie kontekst,
  // więc grubość linii zostaje w px canvasa (≈ px ekranu) mimo różnych skal x/y
  const sx = w / ((r.lonMax - r.lonMin) / 360 * WORLD_W), sy = h / ((r.latMax - r.latMin) / 180 * WORLD_H)
  const x0 = (r.lonMin + 180) / 360 * WORLD_W, y0 = (90 - r.latMax) / 180 * WORLD_H
  const shifted = (src: Path2D) => {
    const out = new Path2D()
    // kopie przesunięte o ±szerokość świata: region może wychodzić poza antymerydian
    for (const k of [-1, 0, 1]) out.addPath(src, new DOMMatrix([sx, 0, 0, sy, (k * WORLD_W - x0) * sx, -y0 * sy]))
    return out
  }
  ctx.fillStyle = token('--map-vec-land', 'beige')
  ctx.fill(shifted(P.land))
  // odcienie państw i krajów na trasie — ciepłe tokeny wektorowe (jak mapa 2D), nie paleta zdjęciowa
  const vars = new Map<string, string>()
  const tok = (name: string) => vars.get(name) ?? (vars.set(name, token(name, 'transparent')), vars.get(name)!)
  for (const { c, p } of P.countries) {
    const fills = [opts.countryColors && vecTintVar(c), opts.highlights && HL[c.id] && VEC_HL_VAR[HL[c.id]]]
    for (const f of fills) if (f) { ctx.fillStyle = tok(f); ctx.fill(shifted(p)) }
  }
  if (relief.length) {
    // rzeźba: szarość 128 neutralna, ciemniej = cień stoku, jaśniej = stok w słońcu
    ctx.save()
    ctx.globalCompositeOperation = 'hard-light'
    ctx.globalAlpha = Number(token('--map-vec-relief', '0.6')) || 0.6
    ctx.imageSmoothingQuality = 'high'
    const kx = w / (r.lonMax - r.lonMin), ky = h / (r.latMax - r.latMin)
    // +1 px zakładki — bez włosowatych szwów między kafelkami
    for (const { tile: t, img } of relief) {
      ctx.drawImage(img, (t.lonMin - r.lonMin) * kx, (r.latMax - t.latMax) * ky, t.dLon * kx + 1, t.dLat * ky + 1)
    }
    ctx.restore()
  }
  const dpr = Math.min(devicePixelRatio || 1, 2) * lineScale
  ctx.lineJoin = 'round'; ctx.lineCap = 'round'
  ctx.strokeStyle = token('--map-vec-border', 'gray'); ctx.lineWidth = 1 * dpr
  ctx.stroke(shifted(P.borders))
  ctx.strokeStyle = token('--map-vec-coast', 'slategray'); ctx.lineWidth = 1.3 * dpr
  ctx.stroke(shifted(P.coast))
}

/** Łata wektorowa w scenie. update(camera) po ruchu kamery → udział 0..1 (do przygaszenia
    zdjęciowych nakładek); onChange → przerysuj klatkę. */
export function createGlobeVector(THREE: Three, scene: Scene, renderer: WebGLRenderer, R: number,
                                  opts: VectorOpts, onChange: () => void) {
  const canvas = document.createElement('canvas')
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = renderer.capabilities.getMaxAnisotropy()
  // nad łatami LOD (≤ R·1,0009), pod nakładką kolorów (R·1,0016) i liniami granic (R·1,0022)
  // Lambert jak kula pod spodem (Phong) — ten sam dzień/noc, bez skoku jasności przy przejściu
  const mat = new THREE.MeshLambertMaterial({ map: tex, transparent: true, opacity: 0, depthWrite: false })
  const mesh = new THREE.Mesh(new THREE.BufferGeometry(), mat)
  mesh.visible = false
  mesh.renderOrder = 1
  scene.add(mesh)
  const maxSide = Math.min(4096, renderer.capabilities.maxTextureSize)
  let drawn: { r: Region; ppd: number } | null = null
  let timer: ReturnType<typeof setTimeout> | undefined

  const redraw = (r: Region, ppd: number) => {
    const { w, h } = regionCanvasSize(r, ppd, maxSide)
    paintVectorRegion(canvas, r, w, h, opts)
    // nowy rozmiar canvasa wymaga nowej tekstury GPU (three nie realokuje sam)
    tex.dispose(); tex.needsUpdate = true
    if (!opts.satellite) {
      // rzeźba terenu dochodzi po wczytaniu kafelków (ten sam region, ten sam rozmiar)
      void loadReliefFor(r, ppd).then(rel => {
        if (drawn?.r !== r || !rel.length) return
        paintVectorRegion(canvas, r, w, h, opts, rel)
        tex.needsUpdate = true
        onChange()
      })
    }
    const lonSpan = r.lonMax - r.lonMin, latSpan = r.latMax - r.latMin
    const seg = (deg: number) => Math.max(8, Math.ceil(deg / 1.5))   // ≤1,5° na segment
    mesh.geometry.dispose()
    mesh.geometry = new THREE.SphereGeometry(R * 1.0012, seg(lonSpan), seg(latSpan),
      (r.lonMin + 180) * DEG, lonSpan * DEG, (90 - r.latMax) * DEG, latSpan * DEG)
    drawn = { r, ppd }
    onChange()
  }

  return {
    update(camera: Camera): number {
      const cam = camera as PerspectiveCamera
      const p = cam.position, dist = p.length()
      const ppd = globePxPerDeg(dist, R, cam.fov, renderer.domElement.height)
      // mapa terenu: łata zastępuje teksturę całej kuli, gdy ta zaczyna się rozmazywać
      const mix = vectorMix(ppd, opts.satellite ? undefined : TERRAIN_TEX_W / 360)
      mat.opacity = mix
      mesh.visible = mix > 0 && drawn != null
      if (mix > 0) {
        const lat = Math.asin(p.y / dist) / DEG
        // odwrotność latLonToVec3 (globeMath) — jak w globeTilesFor
        const lon = ((Math.atan2(p.z, -p.x) / DEG - 180) % 360 + 540) % 360 - 180
        const cap = capRadiusDeg(dist, R, cam.fov, cam.aspect)
        const need = regionFor(lat, lon, cap, 1)
        const stale = !drawn || !covers(drawn.r, need) || ppd / drawn.ppd > 1.4 || ppd / drawn.ppd < 0.6
        clearTimeout(timer)
        if (stale) timer = setTimeout(() => redraw(regionFor(lat, lon, cap), ppd), drawn ? REDRAW_MS : 0)
      }
      return mesh.visible ? mix : 0
    },
    dispose() {
      clearTimeout(timer)
      scene.remove(mesh)
      mesh.geometry.dispose(); mat.dispose(); tex.dispose()
    },
  }
}
