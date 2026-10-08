// Warstwy dekoracyjne mapy trackingu wg makiety Tracking.html:
// podświetlone kraje, nazwy krajów, terminale kontenerowe, etykiety kluczowych
// portów, magazyny docelowe. Wszystko w tej samej liniowej projekcji co WORLD_PATH.
import { WORLD_W } from '../../worldmap'
import {
  COUNTRIES, countryFill, CPORTS_MINOR, HL, HL_FILL, HL_STROKE, KEY_PORTS, PL_NAMES, WAREHOUSES,
  px, py,
} from './mapStatic'

interface View { x: number; y: number; w: number }

/* deterministyczne kolory państw — paleta wspólna z globusem (mapStatic.COUNTRY_PALETTE) */
export function CountryColors({ view }: { view: View }) {
  const s = view.w / WORLD_W
  return (
    <g style={{ pointerEvents: 'none' }}>
      {COUNTRIES.map(c => (
        <path key={`${c.id}-${c.name}`} d={c.path}
              fill={countryFill(c)}
              stroke="rgba(180,205,235,.25)" strokeWidth={0.5 * s} />
      ))}
    </g>
  )
}

export interface FactoryCluster {
  x: number
  y: number
  city: string | null
  suppliers: { id: number; name: string }[]
}

/* podświetlenia krajów — renderowane NAD lądem, pod kreską wybrzeża */
export function CountriesFill({ view }: { view: View }) {
  const s = view.w / WORLD_W
  return (
    <g style={{ pointerEvents: 'none' }}>
      {COUNTRIES.filter(c => HL[c.id]).map(c => (
        <path key={c.id} d={c.path} fill={HL_FILL[HL[c.id]]} stroke={HL_STROKE[HL[c.id]]}
              strokeWidth={1.2 * s} />
      ))}
    </g>
  )
}

interface LabelLine { t: string; size: number; weight: number; fill: string; mono?: boolean }
interface LabelSpec {
  pri: number
  x: number
  y: number
  /* przesunięcie w px ekranu (leader line) — brak = etykieta zakotwiczona w punkcie */
  dx?: number
  dy?: number
  anchor?: 'start' | 'middle' | 'end'
  lines: LabelLine[]
}

interface OverlayProps {
  view: View
  showNames: boolean
  showLabels: boolean
  showAllPorts: boolean
  /* liczba kontenerów per id kluczowego portu (z realnych punktów mapy) */
  portCounts: Map<string, number>
  /* etykiety statków AIS (nazwa przy markerze, z anti-collision) */
  vesselLabels?: { x: number; y: number; name: string }[]
  /* klastry fabryk dostawców per miasto/centroid kraju */
  factories?: FactoryCluster[]
  onFactoryClick?: (f: FactoryCluster) => void
  /* porty kontenerowe ze słownika (GET /api/container-ports?with_coords=true);
     pusto/brak = fallback na statyczną listę z makiety (CPORTS_MINOR) */
  allPortsList?: { name: string; cc: string; lon: number; lat: number }[]
}

// Terminale, etykiety portów, magazyny + greedy anti-collision etykiet (jak w makiecie:
// sortowanie po priorytecie, pierwsza zmieszczona wygrywa).
export default function MapDecorOverlay({ view, showNames, showLabels, showAllPorts, portCounts, vesselLabels, factories, onFactoryClick, allPortsList }: OverlayProps) {
  const s = view.w / WORLD_W          // px świata na px ekranu
  const k = WORLD_W / view.w          // krotność zoomu
  const vx0 = view.x, vx1 = view.x + view.w
  const vy0 = view.y, vy1 = view.y + view.w / 2
  const vis = (x: number, y: number) => x >= vx0 - 40 * s && x <= vx1 + 40 * s && y >= vy0 - 30 * s && y <= vy1 + 30 * s

  const labels: LabelSpec[] = []

  /* --- nazwy krajów --- */
  if (showNames) for (const c of COUNTRIES) {
    const tier = HL[c.id]
    if (!tier && k < 2.2) continue
    if (!vis(c.cx, c.cy)) continue
    const nm = PL_NAMES[c.name]
    if (!nm) continue
    labels.push({
      pri: tier ? 3 : 5, x: c.cx, y: c.cy, anchor: 'middle',
      lines: [{ t: nm.toUpperCase(), size: tier ? 10.5 : 9, weight: 700,
        fill: tier === 'dest' ? 'rgba(255,233,174,.95)' : tier ? 'rgba(222,236,255,.9)' : 'rgba(208,226,248,.6)' }],
    })
  }

  /* --- kluczowe porty: etykieta z leader line --- */
  if (showLabels) for (const p of KEY_PORTS) {
    const x = px(p.lon), y = py(p.lat)
    if (!vis(x, y)) continue
    const isDest = p.role === 'dest'
    const n = portCounts.get(p.id) ?? 0
    labels.push({
      pri: isDest ? 0 : 1, x, y, dx: p.dx, dy: p.dy,
      lines: [
        { t: p.name.toUpperCase(), size: isDest ? 12.5 : 11.5, weight: isDest ? 700 : 600,
          fill: isDest ? '#ffe9ae' : '#eaf4ff' },
        { t: n > 0 ? `${p.id} · ${n} kont.` : p.id, size: 10, weight: 500,
          fill: 'rgba(178,205,238,.92)', mono: true },
      ],
    })
  }

  /* --- nazwy statków AIS --- */
  if (showLabels) for (const v of vesselLabels ?? []) {
    if (!vis(v.x, v.y)) continue
    labels.push({
      pri: 2, x: v.x + 11 * s, y: v.y - 3 * s, anchor: 'start',
      lines: [{ t: v.name, size: 10.5, weight: 600, fill: '#eaf4ff' }],
    })
  }

  /* --- miasta fabryk dostawców (od zoomu 2x) --- */
  if (k >= 2) for (const f of factories ?? []) {
    if (!f.city || !vis(f.x, f.y)) continue
    labels.push({
      pri: 4, x: f.x + 8 * s, y: f.y + 3.5 * s, anchor: 'start',
      lines: [{ t: `${f.city} · ${f.suppliers.length}`, size: 9.4, weight: 600,
        fill: 'rgba(196,238,180,.95)', mono: true }],
    })
  }

  /* --- magazyny docelowe --- */
  if (showLabels) for (const w of WAREHOUSES) {
    const x = px(w.lon), y = py(w.lat)
    if (!vis(x, y)) continue
    labels.push({
      pri: 0, x, y, dx: w.dx, dy: w.dy,
      lines: [
        { t: w.name, size: 11.5, weight: 700, fill: w.color },
        { t: k >= 2 ? w.addr : w.company, size: 9.6, weight: 500,
          fill: 'rgba(200,220,245,.92)', mono: true },
      ],
    })
  }

  /* --- terminale kontenerowe (małe kropki + nazwa od zoomu 2.6x) --- */
  const allPorts = allPortsList?.length ? allPortsList : CPORTS_MINOR
  const dots = showAllPorts
    ? allPorts.filter(p => vis(px(p.lon), py(p.lat)))
    : []
  if (showAllPorts && k >= 2.6) for (const p of dots) {
    labels.push({
      pri: 6, x: px(p.lon) + 6 * s, y: py(p.lat) + 3.2 * s, anchor: 'start',
      lines: [{ t: p.name, size: 8.6, weight: 500, fill: 'rgba(190,225,240,.9)', mono: true }],
    })
  }

  /* --- greedy rozmieszczenie: priorytet rosnąco, kolizja = odpada --- */
  const boxes: [number, number, number, number][] = []
  const fits = (x0: number, y0: number, w: number, h: number) => {
    if (x0 < vx0 + 2 * s || x0 + w > vx1 - 2 * s || y0 < vy0 + 2 * s || y0 + h > vy1 - 2 * s) return false
    for (const b of boxes) if (x0 < b[2] && b[0] < x0 + w && y0 < b[3] && b[1] < y0 + h) return false
    boxes.push([x0, y0, x0 + w, y0 + h])
    return true
  }
  const placed: (LabelSpec & { lx: number; ly: number; textAnchor: string; leader?: string })[] = []
  for (const L of [...labels].sort((a, b) => a.pri - b.pri)) {
    const lh = 12.6 * s
    const wEst = (Math.max(...L.lines.map(l => l.t.length * l.size * (l.mono ? 0.62 : 0.6))) + 6) * s
    const hEst = L.lines.length * lh + 7 * s
    if (L.dx != null && L.dy != null) {
      const right = L.dx >= 0
      const lx = L.x + L.dx * s, ly = L.y + L.dy * s
      if (!fits(right ? lx : lx - wEst, ly - L.lines[0].size * s, wEst, hEst)) continue
      placed.push({ ...L, lx, ly, textAnchor: right ? 'start' : 'end',
        leader: `M${L.x},${L.y} L${lx + (right ? -10 : 10) * s},${ly} L${lx + (right ? -2 : 2) * s},${ly}` })
    } else {
      const anchor = L.anchor ?? 'middle'
      const x0 = anchor === 'middle' ? L.x - wEst / 2 : anchor === 'end' ? L.x - wEst : L.x
      if (!fits(x0, L.y - L.lines[0].size * s, wEst, hEst)) continue
      placed.push({ ...L, lx: L.x, ly: L.y, textAnchor: anchor })
    }
  }

  return (
    <g>
      {/* terminale kontenerowe */}
      {dots.map(p => (
        <circle key={`${p.name}-${p.cc}`} cx={px(p.lon)} cy={py(p.lat)} r={2.6 * s}
                fill="#8fd3e8" stroke="rgba(8,20,36,.9)" strokeWidth={0.9 * s}>
          <title>{`${p.name} · ${p.cc}`}</title>
        </circle>
      ))}
      {/* odcinki lądowe port → magazyn + markery magazynów
          (hardkod z makiety — do podmiany na dane z systemu) */}
      {WAREHOUSES.map(w => (
        <g key={w.id}>
          <path d={`M${px(w.fromLon)},${py(w.fromLat)} L${px(w.lon)},${py(w.lat)}`}
                fill="none" stroke={w.color} strokeWidth={2 * s}
                strokeDasharray={`${2 * s} ${4 * s}`} opacity={0.95} />
          <circle cx={px(w.lon)} cy={py(w.lat)} r={11 * s} fill={w.color} opacity={0.26} />
          <rect x={px(w.lon) - 5.5 * s} y={py(w.lat) - 5.5 * s} width={11 * s} height={11 * s}
                rx={2 * s} fill={w.color} stroke="#fff" strokeWidth={1.6 * s}>
            <title>{`${w.name} · ${w.company}\n${w.addr}`}</title>
          </rect>
        </g>
      ))}
      {/* fabryki dostawców: zielony romb, klaster per miasto z licznikiem */}
      {(factories ?? []).map((f, i) => (
        <g key={i} transform={`translate(${f.x},${f.y})`} style={{ cursor: 'pointer' }}
           onClick={() => onFactoryClick?.(f)}>
          <rect x={-5 * s} y={-5 * s} width={10 * s} height={10 * s}
                transform="rotate(45)" rx={1.5 * s}
                fill="#7ac74f" stroke="#0a1626" strokeWidth={1.2 * s} />
          {f.suppliers.length > 1 && (
            <text y={-7 * s} textAnchor="middle" fill="#c9f2b2"
                  style={{ fontSize: 9 * s, fontWeight: 700, paintOrder: 'stroke',
                           stroke: 'rgba(4,12,24,.85)', strokeWidth: 2.6 * s }}>
              {f.suppliers.length}
            </text>
          )}
          <title>{[f.city, ...f.suppliers.slice(0, 8).map(su => su.name),
            f.suppliers.length > 8 ? `+${f.suppliers.length - 8}` : null]
            .filter(Boolean).join('\n')}</title>
        </g>
      ))}
      {/* kropki kluczowych portów — kotwica leader line etykiety */}
      {showLabels && KEY_PORTS.map(p => (
        <circle key={p.id} cx={px(p.lon)} cy={py(p.lat)} r={3.2 * s}
                fill={p.role === 'dest' ? '#ffd166' : p.role === 'origin' ? '#e9a13b' : '#2f8ef7'}
                stroke="#fff" strokeWidth={1.2 * s} style={{ pointerEvents: 'none' }} />
      ))}
      {/* etykiety (w trybie wektorowym kolor i obwódka z tokenów — .world-map.is-vector w CSS) */}
      <g className="map-labels" style={{ pointerEvents: 'none' }}>
        {placed.map((L, i) => (
          <g key={i}>
            {L.leader && (
              <path d={L.leader} fill="none" stroke="rgba(206,226,250,.5)" strokeWidth={1 * s} />
            )}
            {L.lines.map((l, j) => (
              <text key={j} x={L.lx} y={L.ly + j * 12.6 * s} textAnchor={L.textAnchor as never}
                    fill={l.fill}
                    style={{
                      // NIE font-shorthand: `font: 700 9px inherit` jest niepoprawny
                      // (inherit nie jest font-family) → cała deklaracja odpadała i tekst
                      // renderował się w 16px ŚWIATA (rósł z zoomem, nachodził na siebie)
                      fontSize: l.size * s, fontWeight: l.weight,
                      ...(l.mono ? { fontFamily: 'ui-monospace, monospace' } : null),
                      letterSpacing: '.02em', paintOrder: 'stroke',
                      stroke: 'var(--map-label-halo, rgba(4,12,24,.8))', strokeWidth: 3 * s, strokeLinejoin: 'round',
                    }}>
                {l.t}
              </text>
            ))}
          </g>
        ))}
      </g>
    </g>
  )
}
