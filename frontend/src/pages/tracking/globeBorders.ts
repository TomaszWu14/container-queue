// Granice państw na globusie jako prawdziwe linie 3D (nie wypalone w teksturze 4096 px —
// tam przy zbliżeniu były poszarpanymi schodkami o szerokości ~25 px). Linia w WebGL ma
// stałą szerokość 1 px ekranu przy każdym zoomie. Źródło: world-atlas countries-50m
// (Natural Earth, domena publiczna), topojson.mesh = każda granica raz (bez dublowania
// wspólnych krawędzi sąsiadów). Czysta matematyka — testowalna bez three.js.
import { mesh } from 'topojson-client'
import atlas from 'world-atlas/countries-50m.json'
import { latLonToVec3 } from './globeMath'

type LonLat = [number, number]
const MAX_STEP = 1   // [°] dłuższe odcinki (np. granica USA–Kanada po 49. równoleżniku) dzielimy

/** Polilinie (lon, lat) → pary wierzchołków dla THREE.LineSegments na sferze o promieniu r.
    Odcinki > MAX_STEP stopni zagęszczamy liniowo w lon/lat (granice „po równoleżniku"
    zostają na równoleżniku), żeby cięciwa nie zapadała się pod powierzchnię kuli. */
export function borderSegments(lines: LonLat[][], r: number): Float32Array {
  const out: number[] = []
  const push = (lon: number, lat: number) => { out.push(...latLonToVec3(lat, lon, r)) }
  for (const line of lines) {
    for (let i = 1; i < line.length; i++) {
      const [lon0, lat0] = line[i - 1], [lon1, lat1] = line[i]
      if (Math.abs(lon1 - lon0) > 180) continue          // skok przez antymerydian — nie rysuj w poprzek
      const n = Math.max(1, Math.ceil(Math.max(Math.abs(lon1 - lon0), Math.abs(lat1 - lat0)) / MAX_STEP))
      for (let k = 0; k < n; k++) {
        const a = k / n, b = (k + 1) / n
        push(lon0 + (lon1 - lon0) * a, lat0 + (lat1 - lat0) * a)
        push(lon0 + (lon1 - lon0) * b, lat0 + (lat1 - lat0) * b)
      }
    }
  }
  return new Float32Array(out)
}

let cached: LonLat[][] | null = null
/** Granice wszystkich państw (50m) jako polilinie lon/lat — liczone raz na sesję. */
export function countryBorderLines(): LonLat[][] {
  if (!cached) {
    /* eslint-disable-next-line @typescript-eslint/no-explicit-any */
    const topo = atlas as any
    // filtr a !== b: tylko granice między państwami — wybrzeże ma już zdjęcie NASA
    cached = (mesh(topo, topo.objects.countries, (a: unknown, b: unknown) => a !== b).coordinates as LonLat[][])
  }
  return cached
}
