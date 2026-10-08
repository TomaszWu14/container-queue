// Ostrzejsze zdjęcie Ziemi przy zoomie: piramida kafelków Blue Marble (public/globe/tiles,
// generowane scripts/make_map_tiles.py) — wspólna dla mapy 2D i globusa 3D (globeTiles.ts).
// Poziom 0 = earth-blue-marble-4k.webp (zawsze pod spodem), z1 = 8192 px (8×4 kafelki),
// z2 = 16384 px (16×8), z3 = 32768 px (32×16; kafelki natywne 675 px — limit źródła 21600 px).
// Brak kafelka = sam poziom 0.
import { WORLD_H, WORLD_W } from '../../worldmap'

export const BASE_PX = 4096    // szerokość zdjęcia poziomu 0
export const MAX_Z = 3
const SHARPEN_AT = 1.25        // przełącz poziom, gdy ekran potrzebuje >125% jego pikseli

export const tileCols = (z: number) => 4 * 2 ** z
export const tileHref = (z: number, row: number, col: number) =>
  `${import.meta.env.BASE_URL}globe/tiles/${z}/${row}_${col}.webp`

/** Najniższy poziom (≤ maxZ), którego tekstury wystarcza na `need` px ekranu na px poziomu 0.
    Ta sama reguła dla zdjęcia (MAX_Z) i rzeźby terenu (reliefTiles.ts, RELIEF_MAX_Z). */
export function levelFor(need: number, maxZ = MAX_Z): number {
  let z = 0
  while (z < maxZ && need > 2 ** z * SHARPEN_AT) z++
  return z
}

export interface EarthTile { z: number; row: number; col: number; x: number; y: number; size: number; href: string }

/** Kafelki pokrywające kadr {x, y, w}×viewH (jednostki świata 1000×500) dla ekranu
    screenW px CSS o gęstości dpr (ekran retina/125% potrzebuje proporcjonalnie więcej pikseli). */
export function visibleTiles(view: { x: number; y: number; w: number }, viewH: number,
                             screenW: number, dpr = 1): EarthTile[] {
  const z = levelFor(screenW * dpr / view.w / (BASE_PX / WORLD_W))
  if (z === 0) return []
  const cols = tileCols(z)
  const size = WORLD_W / cols                         // kafelek kwadratowy: rows = cols / 2
  const span = (from: number, len: number, max: number) => {
    const first = Math.max(0, Math.floor(from / size))
    const last = Math.min(max - 1, Math.ceil((from + len) / size) - 1)
    return Array.from({ length: Math.max(0, last - first + 1) }, (_, i) => first + i)
  }
  const tiles: EarthTile[] = []
  for (const row of span(view.y, viewH, WORLD_H / size)) {
    for (const col of span(view.x, view.w, cols)) {
      tiles.push({ z, row, col, x: col * size, y: row * size, size, href: tileHref(z, row, col) })
    }
  }
  return tiles
}
