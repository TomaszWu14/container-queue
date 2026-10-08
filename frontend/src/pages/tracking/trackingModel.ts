import { WORLD_H, WORLD_W } from '../../worldmap'
import type { MapWatcher } from './AvatarStack'
import type { FactoryCluster } from './MapDecor'
import { KEY_PORTS, supplierCoords } from './mapStatic'
import { CONTAINER_STATUSES } from '../../types/core'
import type { Vessel } from './types'

// Model danych mapy trackingu: kształty odpowiedzi API, palety kolorów, projekcja 2D
// i czyste wyliczenia (klastry punktów, liczniki portów, klastry fabryk).

export interface MapPoint {
  id: number
  container_no: string
  vessel: string
  status: string
  eta: string | null
  etd: string | null
  location: string
  event: string
  occurred_at: string | null
  is_special?: boolean
  lat?: number
  lon?: number
  watchers?: MapWatcher[]
}

export interface MapData {
  points: MapPoint[]
  unlocated: MapPoint[]
  tracked: number
  total: number
}

export type RoutePoint = { lat: number; lon: number; wind_kmh: number | null; wind_dir: number | null; wave_m: number | null }
export type VesselWeather = { wind_kmh: number | null; wind_dir: number | null; wave_m: number | null; route?: RoutePoint[] }
// kongestia portów: trend 14 dni + flaga alertu (dziś > 2× mediana)
export type PortCongestion = { port: string; alert: boolean; days: { day: string; waiting: number }[] }
export type SupplierRow = { id: number; name: string; country: string; address: string }
export type ContainerPortPos = { name: string; cc: string; lon: number; lat: number }

// Kolory spółek i statusów na mapie = tokeny z 00-tokens.css (audyt S6: jedno źródło, bez kopii w TS).
export const MAP_COMPANIES = ['ACME', 'BOREALIS', 'COBALT', 'PT', 'DLT', 'TRANZYT']
// karta statku to panel w motywie strony z białym tekstem → wypełnienie -fill (to samo w obu motywach)
export const COMPANY_FILL: Record<string, string> = Object.fromEntries(
  MAP_COMPANIES.map(c => [c, `var(--co-${c.toLowerCase()}-fill)`]))

export type MapPalette = { status: Record<string, string>; company: Record<string, string>; ink: string }
// Mapa (globus i 2D) jest zawsze ciemna, więc bierze warianty ciemnego motywu niezależnie od motywu
// strony: sonda z klasą .theme-dark (ten sam blok tokenów co :root[data-theme='dark']). Canvas globusa
// potrzebuje wartości, nie var(). `ink` = tło ciemnego motywu — tekst na jasnej kropce statusu.
export function readMapPalette(): MapPalette {
  const probe = document.createElement('span')
  probe.className = 'theme-dark'
  probe.hidden = true
  document.body.appendChild(probe)
  const cs = getComputedStyle(probe)
  const pick = (keys: readonly string[], prop: (k: string) => string) => Object.fromEntries(
    keys.map(k => [k, cs.getPropertyValue(prop(k)).trim()]).filter(([, v]) => v))
  const palette = {
    status: pick(CONTAINER_STATUSES, s => `--st-${s}-ink`),
    company: pick(MAP_COMPANIES, c => `--co-${c.toLowerCase()}`),
    ink: cs.getPropertyValue('--bg').trim() || 'black',
  }
  probe.remove()
  return palette
}

export const project = (lat: number, lon: number) => ({
  x: (lon + 180) / 360 * WORLD_W,
  y: (90 - lat) / 180 * WORLD_H,
})

// siatka geograficzna co 10° w tej samej liniowej projekcji — jeden statyczny path
export const GRID_PATH = (() => {
  let d = ''
  for (let i = 1; i < 36; i++) d += `M${(i * WORLD_W / 36).toFixed(1)},0V${WORLD_H}`
  for (let i = 1; i < 18; i++) d += `M0,${(i * WORLD_H / 18).toFixed(1)}H${WORLD_W}`
  return d
})()

// klastrowanie zależne od zoomu: punkty bliżej niż clusterDist (jednostki świata)
// zlewają się w jeden badge z licznikiem (przy dużym zbliżeniu rozpadają się na pojedyncze)
export function clusterPoints(points: MapPoint[], clusterDist: number) {
  const grouped = new Map<string, MapPoint[]>()
  // W9: klucz klastra zapisany per-punkt (po id) — grupa jest kluczowana współrzędnymi
  // PIERWSZEGO punktu, więc lookup po współrzędnych punktu AKTYWNEGO (nie-pierwszego
  // w klastrze) gubił "+N"; ten Map trzyma prawdziwy klucz niezależnie od tego, który
  // punkt klastra jest aktywny
  const pointClusterKey = new Map<number, string>()
  const centers: { x: number; y: number; key: string }[] = []
  for (const point of points) {
    const p = project(point.lat!, point.lon!)
    const hit = centers.find(c => Math.hypot(c.x - p.x, c.y - p.y) < clusterDist)
    const key = hit ? hit.key : `${point.lat},${point.lon}`
    if (!hit) centers.push({ ...p, key })
    if (!grouped.has(key)) grouped.set(key, [])
    grouped.get(key)!.push(point)
    pointClusterKey.set(point.id, key)
  }
  return { grouped, pointClusterKey }
}

// kluczowe porty: liczba kontenerów z realnych punktów mapy (dopasowanie po
// bliskości współrzędnych, ~0.7°) + nasze statki „na redzie" z vessels.near_port
export function keyPortStats(points: MapPoint[], vessels: Vessel[]) {
  const portCounts = new Map<string, number>()
  for (const point of points) {
    if (point.lat == null || point.lon == null) continue
    const hit = KEY_PORTS.find(p =>
      Math.abs(p.lat - point.lat!) < 0.7 && Math.abs(p.lon - point.lon!) < 0.7)
    if (hit) portCounts.set(hit.id, (portCounts.get(hit.id) ?? 0) + 1)
  }
  const portAnchored = new Map<string, number>()
  for (const v of vessels) {
    if (!v.near_port || (v.sog ?? 0) >= 1) continue
    const hit = KEY_PORTS.find(p => p.ais.includes(v.near_port!.toUpperCase()))
    if (hit) portAnchored.set(hit.id, (portAnchored.get(hit.id) ?? 0) + 1)
  }
  const chipPorts = KEY_PORTS
    .filter(p => (portAnchored.get(p.id) ?? 0) > 0 || (portCounts.get(p.id) ?? 0) > 0)
    .sort((a, b) => (portAnchored.get(b.id) ?? 0) - (portAnchored.get(a.id) ?? 0)
      || (portCounts.get(b.id) ?? 0) - (portCounts.get(a.id) ?? 0))
  return { portCounts, portAnchored, chipPorts }
}

// klastry fabryk per pozycja (miasto z adresu albo centroid kraju)
export function factoryClusters(suppliers: SupplierRow[]) {
  const factories: FactoryCluster[] = []
  const byKey = new Map<string, FactoryCluster>()
  for (const su of suppliers) {
    const pos = supplierCoords(su.address, su.country)
    if (!pos) continue
    const key = `${pos.x.toFixed(1)},${pos.y.toFixed(1)}`
    let f = byKey.get(key)
    if (!f) { f = { x: pos.x, y: pos.y, city: pos.city, suppliers: [] }; byKey.set(key, f); factories.push(f) }
    f.suppliers.push({ id: su.id, name: su.name })
  }
  return factories
}
