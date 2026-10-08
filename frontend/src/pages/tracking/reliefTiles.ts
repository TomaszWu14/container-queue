// Cieniowana rzeźba terenu pod mapą wektorową (decyzja usera 2026-10-01: „mapa terenu, nie
// obrazek"). Źródło: Natural Earth SR_HR (domena publiczna) pocięte scripts/make_map_tiles.py
// --relief na piramidę public/globe/relief: z0 = relief-4k.webp (4096 px), z1 = 8192 px (8×4
// kafelki 1024 px), z2 = 16384 px (16×8). Szarość 128 = teren płaski i morze — mieszanie
// hard-light zostawia je bez zmian, więc rzeźba nie potrzebuje maski lądu. Rzeźba jest gładka,
// więc powiększenie ponad z2 wygląda naturalnie (w przeciwieństwie do zdjęcia).
import { levelFor, tileCols } from './earthTiles'
import type { Region } from './vectorMap'

const BASE = `${import.meta.env.BASE_URL}globe/relief/`
export const RELIEF_BASE_PX = 4096
export const RELIEF_MAX_Z = 2

export interface ReliefTile { href: string; lonMin: number; latMax: number; dLon: number; dLat: number }

/** Poziom piramidy dla gęstości ppd [px/°] — ta sama reguła co zdjęcie (levelFor), sufit z2. */
export const reliefLevel = (ppd: number) => levelFor(ppd / (RELIEF_BASE_PX / 360), RELIEF_MAX_Z)

/** Kafelki rzeźby pokrywające region (długość może wychodzić poza ±180 — kafelki wtedy
    powtarzamy z przesunięciem, href zawinięty). z0 = jeden obraz całego świata. */
export function reliefTilesFor(r: Region, ppd: number): ReliefTile[] {
  const z = reliefLevel(ppd)
  if (z === 0) {
    const out: ReliefTile[] = []
    for (const k of [-360, 0, 360]) {
      if (r.lonMax > -180 + k && r.lonMin < 180 + k) out.push({ href: `${BASE}relief-4k.webp`, lonMin: -180 + k, latMax: 90, dLon: 360, dLat: 180 })
    }
    return out
  }
  const cols = tileCols(z), deg = 360 / cols
  const rows = cols / 2
  const out: ReliefTile[] = []
  const r0 = Math.max(0, Math.floor((90 - r.latMax) / deg)), r1 = Math.min(rows - 1, Math.ceil((90 - r.latMin) / deg) - 1)
  const c0 = Math.floor((r.lonMin + 180) / deg), c1 = Math.ceil((r.lonMax + 180) / deg) - 1
  for (let row = r0; row <= r1; row++) {
    for (let c = c0; c <= c1; c++) {
      const col = ((c % cols) + cols) % cols
      out.push({ href: `${BASE}tiles/${z}/${row}_${col}.webp`, lonMin: -180 + c * deg, latMax: 90 - row * deg, dLon: deg, dLat: deg })
    }
  }
  return out
}

const cache = new Map<string, Promise<HTMLImageElement>>()
/** Obraz kafelka (cache na sesję; błąd → odrzucenie i ponowna próba przy następnym użyciu). */
export function loadRelief(href: string): Promise<HTMLImageElement> {
  let p = cache.get(href)
  if (!p) {
    p = new Promise((resolve, reject) => {
      const img = new Image()
      img.decoding = 'async'
      img.onload = () => resolve(img)
      img.onerror = () => { cache.delete(href); reject(new Error(href)) }
      img.src = href
    })
    cache.set(href, p)
  }
  return p
}

export type LoadedRelief = { tile: ReliefTile; img: HTMLImageElement }[]

/** Wczytane kafelki dla regionu; brakujące (offline) pomijamy — mapa zostaje bez rzeźby. */
export async function loadReliefFor(r: Region, ppd: number): Promise<LoadedRelief> {
  const tiles = reliefTilesFor(r, ppd)
  const imgs = await Promise.all(tiles.map(t => loadRelief(t.href).catch(() => null)))
  return tiles.flatMap((tile, i) => (imgs[i] ? [{ tile, img: imgs[i]! }] : []))
}
