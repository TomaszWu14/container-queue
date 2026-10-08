// LOD tekstury globusa: przy zbliżeniu powierzchnię pod kamerą pokrywają łaty sfery
// z kafelkami Blue Marble (te same pliki co mapa 2D — earthTiles.ts), nad bazowym
// zdjęciem 4k. Ładujemy tylko kafelki w kadrze (czasza widoczna z kamery), max 4 naraz,
// a niepotrzebne zwalniamy (dispose tekstury i geometrii) — pamięć GPU rośnie tylko
// o kilkanaście kafelków. Poprzedni poziom zostaje, dopóki nowy się nie wczyta (bez mignięć).
// Matematyka (poziom, czasza, wybór kafelków) czysta — testowana bez three.js.
import type { Camera, PerspectiveCamera, Scene, Texture, WebGLRenderer } from 'three'
import { BASE_PX, levelFor, tileCols, tileHref } from './earthTiles'
import { globePxPerDeg } from './vectorMap'

type Three = typeof import('three')
const DEG = Math.PI / 180
const MAX_TILES = 24          // więcej kafelków w kadrze → niższy poziom (i tak by nie było widać)
const MAX_INFLIGHT = 4

/** Poziom piramidy dla kamery w odległości dist od środka kuli R (fov pionowy w °,
    hPx = wysokość bufora rysowania w px). Gęstość w punkcie pod kamerą = globePxPerDeg. */
export function globeLevel(dist: number, R: number, fovDeg: number, hPx: number): number {
  return levelFor(globePxPerDeg(dist, R, fovDeg, hPx) / (BASE_PX / 360))
}

/** Promień kątowy [°] widocznej czaszy kuli: do narożnika ekranu albo do horyzontu. */
export function capRadiusDeg(dist: number, R: number, fovDeg: number, aspect: number): number {
  const beta = Math.atan(Math.tan(fovDeg * DEG / 2) * Math.hypot(1, aspect))
  const s = dist * Math.sin(beta) / R
  const rad = s >= 1 ? Math.acos(R / dist) : Math.asin(s) - beta
  return rad / DEG
}

const gcDeg = (lat1: number, lon1: number, lat2: number, lon2: number) => {
  const c = Math.sin(lat1 * DEG) * Math.sin(lat2 * DEG) +
    Math.cos(lat1 * DEG) * Math.cos(lat2 * DEG) * Math.cos((lon2 - lon1) * DEG)
  return Math.acos(Math.min(1, Math.max(-1, c))) / DEG
}

export interface GlobeTile { z: number; row: number; col: number }

/** Kafelki poziomu z dotykające czaszy (środek lat/lon, promień capDeg). Punkt kafelka
    najbliższy środkowi = środek przycięty do prostokąta lat/lon kafelka (z zawinięciem
    długości); +1 stopień zapasu na tę aproksymację. Najbliższe środkowi pierwsze. */
export function tilesInCap(z: number, lat: number, lon: number, capDeg: number): GlobeTile[] {
  const cols = tileCols(z), span = 360 / cols
  const out: (GlobeTile & { d: number })[] = []
  for (let row = 0; row < cols / 2; row++) {
    const latMax = 90 - row * span, latMin = latMax - span
    const nLat = Math.min(latMax, Math.max(latMin, lat))
    for (let col = 0; col < cols; col++) {
      const lonMin = -180 + col * span
      const off = ((lon - lonMin) % 360 + 360) % 360            // 0..360 na wschód od krawędzi
      const nLon = off <= span ? lon : (off - span < 360 - off ? lonMin + span : lonMin)
      const d = gcDeg(lat, lon, nLat, nLon)
      if (d <= capDeg + 1) out.push({ z, row, col, d })
    }
  }
  return out.sort((a, b) => a.d - b.d).map(({ z, row, col }) => ({ z, row, col }))
}

/** Kafelki do pokazania dla kamery — [] gdy wystarcza bazowe zdjęcie 4k (poziom 0). */
export function globeTilesFor(cam: [number, number, number], R: number, fovDeg: number,
                              aspect: number, hPx: number): GlobeTile[] {
  const dist = Math.hypot(cam[0], cam[1], cam[2])
  const lat = Math.asin(cam[1] / dist) / DEG
  // odwrotność latLonToVec3 (globeMath): x = -sinφ·cosθ, z = sinφ·sinθ, θ = lon + 180°
  const lon = ((Math.atan2(cam[2], -cam[0]) / DEG - 180) % 360 + 540) % 360 - 180
  const cap = capRadiusDeg(dist, R, fovDeg, aspect)
  for (let z = globeLevel(dist, R, fovDeg, hPx); z > 0; z--) {
    const tiles = tilesInCap(z, lat, lon, cap)
    if (tiles.length <= MAX_TILES) return tiles
  }
  return []
}

/** Warstwa łat LOD w scenie. update(camera) po każdym ruchu kamery; onChange → przerysuj. */
export function createGlobeTiles(THREE: Three, scene: Scene, renderer: WebGLRenderer,
                                 R: number, onChange: () => void) {
  const group = new THREE.Group()
  scene.add(group)
  const loader = new THREE.TextureLoader()
  const aniso = renderer.capabilities.getMaxAnisotropy()
  type Entry = { mesh: InstanceType<typeof THREE.Mesh> | null; tex: Texture | null; done: boolean }
  const tiles = new Map<string, Entry>()
  let want: string[] = []
  let queue: GlobeTile[] = []
  let inflight = 0
  let disposed = false
  const key = (t: GlobeTile) => `${t.z}/${t.row}_${t.col}`

  const drop = (k: string) => {
    const e = tiles.get(k)
    if (!e) return
    if (e.mesh) { group.remove(e.mesh); e.mesh.geometry.dispose(); (e.mesh.material as InstanceType<typeof THREE.Material>).dispose() }
    e.tex?.dispose()
    tiles.delete(k)
  }
  // stare łaty zostają, dopóki wszystkie potrzebne nie są gotowe — wtedy sprzątamy
  const prune = () => {
    if (!want.every(k => tiles.get(k)?.done)) return
    const keep = new Set(want)
    for (const k of [...tiles.keys()]) if (!keep.has(k)) drop(k)
  }
  const load = (t: GlobeTile) => {
    const k = key(t)
    const entry: Entry = { mesh: null, tex: null, done: false }
    tiles.set(k, entry)
    inflight++
    const finish = () => { inflight--; entry.done = true; prune(); pump() }
    loader.load(tileHref(t.z, t.row, t.col), tex => {
      if (disposed || tiles.get(k) !== entry) { tex.dispose(); inflight--; pump(); return }
      tex.colorSpace = THREE.SRGBColorSpace
      tex.anisotropy = aniso
      const cols = tileCols(t.z), span = 2 * Math.PI / cols
      const seg = Math.max(8, Math.ceil(360 / cols / 1.5))      // ≤1,5° na segment
      // UV łaty SphereGeometry biegną 0..1 w jej zakresie phi/theta = cały kafelek;
      // promień nieco nad kulą bazową (jej cięciwy 3,75° zapadają się o ~5e-4·R),
      // wyższy poziom wyżej — rysuje się nad niższym bez walki głębokości
      const g = new THREE.SphereGeometry(R * (1.0006 + t.z * 0.0001), seg, seg,
        t.col * span, span, t.row * span, span)
      const mesh = new THREE.Mesh(g, new THREE.MeshPhongMaterial({ map: tex, shininess: 8,
        specular: new THREE.Color(0x111111) }))
      entry.mesh = mesh; entry.tex = tex
      group.add(mesh)
      onChange()
      finish()
    }, undefined, () => {
      if (tiles.get(k) === entry) finish(); else { inflight--; pump() }   // brak pliku → zostaje baza
    })
  }
  const pump = () => {
    while (!disposed && inflight < MAX_INFLIGHT && queue.length) {
      const t = queue.shift()!
      if (!tiles.has(key(t))) load(t)
    }
  }

  return {
    update(camera: Camera) {
      const cam = camera as PerspectiveCamera
      const next = globeTilesFor([cam.position.x, cam.position.y, cam.position.z], R,
        cam.fov, cam.aspect, renderer.domElement.height)
      const nextKeys = next.map(key)
      if (nextKeys.join() === want.join()) return
      want = nextKeys
      // nieskończone ładowania spoza kadru anulujemy (wynik zostanie wyrzucony)
      const keep = new Set(want)
      for (const [k, e] of [...tiles]) if (!e.done && !keep.has(k)) tiles.delete(k)
      queue = next.filter(t => !tiles.has(key(t)))
      prune()
      pump()
    },
    dispose() {
      disposed = true
      for (const k of [...tiles.keys()]) drop(k)
      scene.remove(group)
    },
  }
}
