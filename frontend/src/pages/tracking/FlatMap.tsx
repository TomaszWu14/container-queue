import { StarIcon } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { WORLD_H, WORLD_W } from '../../worldmap'
import AvatarStack, { uniqueWatchers } from './AvatarStack'
import { EARTH_PHOTO_URL } from './earthPhoto'
import { visibleTiles } from './earthTiles'
import VesselIcon from './VesselIcon'
import { GhostMarker } from './VesselReplay'
import { splitTrailSegments } from './mapUtils'
import MapDecorOverlay, { CountriesFill, CountryColors, type FactoryCluster } from './MapDecor'
import { COUNTRIES, HL, LAND_PATH } from './mapStatic'
import { reliefTilesFor } from './reliefTiles'
import { flatPxPerDeg, VEC_HL_VAR, vecTintVar, vectorMix, vectorPaths } from './vectorMap'
import { replayPointAt } from './globeMath'
import type { MapLayersState } from './MapLayers'
import type { MapView } from './useMapView'
import {
  GRID_PATH, project, readMapPalette,
  type ContainerPortPos, type MapPoint, type VesselWeather,
} from './trackingModel'
import type { Vessel } from './types'

// Płaska mapa 2D (SVG) trackingu — wydzielona z TrackingPage. Stan (widok, aktywny punkt,
// aktywny statek) trzyma strona; tu tylko rysowanie i interakcje myszy/klawiatury.
export default function FlatMap({
  mv, layers, grouped, vessels, weather, active, setActive, pinned, setPinned,
  activeVessel, setActiveVessel, replayOpen, replayIndex, portCounts, containerPorts,
  factories, onFactoryClick,
}: {
  mv: MapView
  layers: MapLayersState
  grouped: Map<string, MapPoint[]>
  vessels: Vessel[]
  weather: Record<number, VesselWeather>
  active: MapPoint | null
  setActive: (p: MapPoint | null) => void
  pinned: boolean
  setPinned: (v: boolean) => void
  activeVessel: Vessel | null
  setActiveVessel: React.Dispatch<React.SetStateAction<Vessel | null>>
  replayOpen: boolean
  replayIndex: number
  portCounts: Map<string, number>
  containerPorts: ContainerPortPos[]
  factories: FactoryCluster[]
  onFactoryClick: (f: FactoryCluster) => void
}) {
  const { view, setView, viewH, svgRef, attachSvg, svgW, zoomCenter } = mv
  const { showCountryColors, showCountries, showGrid, showVessels, showWeather,
          showNames, showPortLabels, showAllPorts, showSatellite } = layers
  const dragRef = useRef<{ px: number; py: number; x: number; y: number } | null>(null)
  // kolory statusów/spółek z tokenów ciemnego motywu (mapa jest zawsze ciemna) — raz na montaż
  const palette = useMemo(readMapPalette, [])
  // zdjęcie satelitarne w tle; false po błędzie wczytania → wektorowy fallback z kreską wybrzeża
  const [photoOk, setPhotoOk] = useState(true)
  // domyślnie mapa terenu (wektor + rzeźba) przy każdym zoomie; z warstwą „Zdjęcie satelitarne"
  // zdjęcie z daleka i płynne przejście w mapę z bliska (próg — vectorMap.ts)
  const dpr = window.devicePixelRatio || 1
  const ppd = flatPxPerDeg(view.w, svgW, dpr)
  const vec = showSatellite ? vectorMix(ppd) : 1
  const vp = useMemo(vectorPaths, [])
  const photoOn = showSatellite && photoOk && vec < 1
  const relief = showSatellite ? [] : reliefTilesFor({
    lonMin: view.x / WORLD_W * 360 - 180, lonMax: (view.x + view.w) / WORLD_W * 360 - 180,
    latMax: 90 - view.y / WORLD_H * 180, latMin: 90 - (view.y + viewH) / WORLD_H * 180,
  }, ppd)
  return (
    <svg ref={attachSvg} viewBox={`${view.x} ${view.y} ${view.w} ${viewH}`}
         className={`world-map${vec >= 0.5 ? ' is-vector' : ''}`}
         style={{ cursor: dragRef.current ? 'grabbing' : 'grab', touchAction: 'none' }}
         onPointerDown={e => {
           // pan tylko z tła mapy — markery mają własne kliki
           if ((e.target as Element).closest('g[role="button"], g.vessel-marker')) return
           dragRef.current = { px: e.clientX, py: e.clientY, x: view.x, y: view.y }
           ;(e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId)
         }}
         onPointerMove={e => {
           const d = dragRef.current
           const svg = svgRef.current
           if (!d || !svg) return
           const rect = svg.getBoundingClientRect()
           const h = view.w * (WORLD_H / WORLD_W)
           setView(v => ({ ...v,
             x: Math.min(Math.max(0, d.x - (e.clientX - d.px) / rect.width * v.w), WORLD_W - v.w),
             y: Math.min(Math.max(0, d.y - (e.clientY - d.py) / rect.height * h), WORLD_H - h) }))
         }}
         onPointerUp={() => { dragRef.current = null }}
         onMouseLeave={() => { if (!pinned) setActive(null) }}>
      {/* tło: zdjęcie satelitarne NASA (to samo co globus, ta sama projekcja 1000x500).
          Wektorowy ocean/ląd pod spodem = widok do czasu wczytania i fallback przy błędzie */}
      <defs>
        <radialGradient id="map-ocean" cx="52%" cy="42%" r="78%">
          <stop offset="0%" stopColor="#123a63" />
          <stop offset="45%" stopColor="#0c2846" />
          <stop offset="100%" stopColor="#05101f" />
        </radialGradient>
        <linearGradient id="map-terra" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#e9f0f3" />
          <stop offset="0.09" stopColor="#aab5a4" />
          <stop offset="0.16" stopColor="#556e44" />
          <stop offset="0.24" stopColor="#5d7c43" />
          <stop offset="0.315" stopColor="#8b9557" />
          <stop offset="0.365" stopColor="#cbb47c" />
          <stop offset="0.43" stopColor="#a79f5d" />
          <stop offset="0.5" stopColor="#3f6a33" />
          <stop offset="0.575" stopColor="#6f8042" />
          <stop offset="0.645" stopColor="#b29a67" />
          <stop offset="0.71" stopColor="#7d8a4e" />
          <stop offset="0.8" stopColor="#8b9880" />
          <stop offset="0.93" stopColor="#dfe7ea" />
          <stop offset="1" stopColor="#f3f7f8" />
        </linearGradient>
        <filter id="map-shelf" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="5" />
        </filter>
      </defs>
      {showSatellite && <>
        <rect width={WORLD_W} height={WORLD_H} fill="url(#map-ocean)" />
        <path d={LAND_PATH} fill="#2d6ea8" opacity="0.45" filter="url(#map-shelf)" />
        <path d={LAND_PATH} fill="url(#map-terra)" />
      </>}
      {photoOn && (
        <image href={EARTH_PHOTO_URL} x={0} y={0} width={WORLD_W} height={WORLD_H}
               preserveAspectRatio="none" onError={() => setPhotoOk(false)} />
      )}
      {/* ostrzejsze kafelki przy zoomie (earthTiles.ts); lekki zakład 0,4% ukrywa szwy */}
      {photoOn && visibleTiles(view, viewH, svgW, dpr).map(tile => (
        <image key={`${tile.z}-${tile.row}-${tile.col}`} href={tile.href} x={tile.x} y={tile.y}
               width={tile.size * 1.004} height={tile.size * 1.004} preserveAspectRatio="none" />
      ))}
      {/* mapa wektorowa: morze, ląd, granice, wybrzeże — kreski stałej grubości ekranowej */}
      {vec > 0 && (
        <g className="map-vector" opacity={vec} style={{ pointerEvents: 'none' }}>
          <rect width={WORLD_W} height={WORLD_H} style={{ fill: 'var(--map-vec-sea)' }} />
          <path d={LAND_PATH} style={{ fill: 'var(--map-vec-land)' }} />
          {/* kolory państw i kraje na trasie — własne ciepłe tokeny (paleta zdjęciowa ma błękity,
              które na jasnym lądzie zlewały się z morzem); kreski wybrzeża NAD wypełnieniami */}
          {showCountryColors && COUNTRIES.map(c => (
            <path key={`${c.id}-${c.name}`} d={c.path} style={{ fill: `var(${vecTintVar(c)})` }} />
          ))}
          {showCountries && COUNTRIES.filter(c => HL[c.id]).map(c => (
            <path key={`hl-${c.id}`} d={c.path} style={{ fill: `var(${VEC_HL_VAR[HL[c.id]]})` }} />
          ))}
          {/* cieniowana rzeźba (Natural Earth): szarość 128 neutralna dla hard-light — morze bez zmian */}
          {relief.map(t => (
            <image key={`${t.href}@${t.lonMin}`} href={t.href} preserveAspectRatio="none"
                   x={(t.lonMin + 180) / 360 * WORLD_W} y={(90 - t.latMax) / 180 * WORLD_H}
                   width={t.dLon / 360 * WORLD_W * 1.002} height={t.dLat / 180 * WORLD_H * 1.002}
                   style={{ mixBlendMode: 'hard-light', opacity: 'var(--map-vec-relief)' }} />
          ))}
          <path d={vp.borders} fill="none" vectorEffect="non-scaling-stroke"
                style={{ stroke: 'var(--map-vec-border)', strokeWidth: 1 }} />
          <path d={vp.coast} fill="none" vectorEffect="non-scaling-stroke" strokeLinejoin="round"
                style={{ stroke: 'var(--map-vec-coast)', strokeWidth: 1.3 }} />
        </g>
      )}
      {/* kolory państw (deterministyczna paleta) pod podświetleniami HL */}
      {/* podświetlenia krajów na trasie (makieta HL) — topojson w tej samej projekcji;
          w trybie wektorowym gasną razem ze zdjęciem (wektor ma własne wypełnienia) */}
      {vec < 1 && (
        <g opacity={1 - vec}>
          {showCountryColors && <CountryColors view={view} />}
          {showCountries && <CountriesFill view={view} />}
        </g>
      )}
      {/* kreska wybrzeża tylko na wektorowym fallbacku — zdjęcie ma własny brzeg (jak globus) */}
      {showSatellite && !photoOk && (
        <path d={LAND_PATH} fill="none" stroke="rgba(226, 240, 255, 0.55)"
              strokeWidth={0.7 * (view.w / WORLD_W)} />
      )}
      {showGrid && (
        <path d={GRID_PATH} fill="none" stroke="rgba(140, 180, 225, 0.22)"
              strokeWidth={0.5 * (view.w / WORLD_W)} />
      )}
      {[...grouped.entries()].map(([key, points]) => {
        const { x, y } = project(points[0].lat!, points[0].lon!)
        const isActive = active != null && points.some(p => p.id === active.id)
        const pin = () => {
          // klaster wielu lokalizacji: klik = przybliżenie, nie tooltip
          if (points.length > 1 && new Set(points.map(p => `${p.lat},${p.lon}`)).size > 1) {
            zoomCenter(0.45)
            return
          }
          setActiveVessel(null); setActive(points[0]); setPinned(true)
        }
        return (
          <g key={key} transform={`translate(${x},${y})`}
             tabIndex={0} role="button"
             aria-label={`${points[0].container_no} — ${points[0].location}`}
             aria-describedby={isActive ? 'map-active-tooltip' : undefined}
             onMouseEnter={() => { if (!pinned) setActive(points[0]) }}
             onFocus={() => { if (!pinned) setActive(points[0]) }}
             onClick={pin}
             onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pin() } }}
             style={{ cursor: 'pointer' }}>
            <circle r={isActive ? 9 : 7} fill={palette.status[points[0].status] ?? '#3b82f6'}
                    fillOpacity="0.9"
                    stroke={points.some(p => p.is_special) ? '#d92d20' : '#fff'}
                    strokeWidth={points.some(p => p.is_special) ? 2.2 : 1.4} />
            <text y="3.4" textAnchor="middle"
                  style={{ fontSize: 8, fontWeight: 700, fill: palette.ink, pointerEvents: 'none' }}>
              {points.length}
            </text>
            <AvatarStack idPrefix={`c${key}`} watchers={uniqueWatchers(points)} r={4.5} />
          </g>
        )
      })}
      {/* warstwa AIS: trasa przebyta + wskaźnik kursu + pilność + spółki */}
      {showVessels && vessels.filter(v => v.lat != null && v.lon != null).map(v => {
        const { x, y } = project(v.lat!, v.lon!)
        // skala odwrotna do zoomu — marker ma stały rozmiar ekranowy
        const s = view.w / WORLD_W
        // K3: trasa przecinająca antymerydian (180°/-180°) dzielona na segmenty —
        // inaczej jedna polilinia rysuje fałszywą linię w poprzek całej mapy
        const trailSegments = splitTrailSegments<[number, number]>([...v.trail, [v.lat!, v.lon!]])
          .map(seg => seg.map(([la, lo]) => project(la, lo)))
        return (
          <g key={`vessel-${v.id}`} className="vessel-marker" style={{ cursor: 'pointer' }}
             onClick={() => { setActive(null); setPinned(false); setActiveVessel(av => av?.id === v.id ? null : v) }}>
            {trailSegments.map((seg, i) => seg.length > 1 && (
              <polyline key={i} points={seg.map(p => `${p.x},${p.y}`).join(' ')}
                        fill="none" stroke="#f5a623" strokeWidth={0.9 * s}
                        strokeDasharray={`${3 * s} ${2.4 * s}`} strokeOpacity="0.5" />
            ))}
            {/* mniejsza sylwetka (×0.75) — przy zagęszczeniu w Europie duże ikony
                zlewały się w pomarańczowy klaster */}
            <g transform={`translate(${x},${y}) scale(${s * 0.75})`}>
              <AvatarStack idPrefix={`v${v.id}`} watchers={v.watchers ?? []} r={6} />
              {activeVessel?.id === v.id && (
                <circle r="11" fill="none" stroke="#f5a623" strokeWidth="1.6"
                        strokeDasharray="3 2" />
              )}
              {showWeather && weather[v.id]?.wind_dir != null && (
                // strzałka wiatru: DOKĄD wieje (dir meteo = skąd, stąd +180°)
                <g transform={`rotate(${(weather[v.id].wind_dir! + 180) % 360})`}
                   opacity="0.85">
                  <path d="M0,-16 L0,-24 M-2.5,-21 L0,-24 L2.5,-21" fill="none"
                        stroke={(weather[v.id].wind_kmh ?? 0) > 50 ? '#d92d20' : '#0e8a6a'}
                        strokeWidth="1.6" strokeLinecap="round" />
                </g>
              )}
              <g transform={`rotate(${v.cog ?? 0})`}>
                <VesselIcon />
              </g>
              {/* nad strzałką: pilność (czerwona kropka) + kropki spółek */}
              {v.delayed > 0 && (
                <circle cx="0" cy="-11.5" r="3" fill="#d92d20" stroke="#fff" strokeWidth="0.8" />
              )}
              {/* gwiazdka nad wszystkim: statek wiezie mój obserwowany kontener */}
              {(v.watched?.length ?? 0) > 0 && (
                <StarIcon className="vessel-watch-star" size={9} strokeWidth={1.6} x={-4.5}
                          y={v.delayed > 0 ? -29 : v.companies.length > 0 ? -23 : -17} aria-hidden="true" />
              )}
              {v.companies.map((code, i) => (
                <circle key={code} r="2.4"
                        cx={(i - (v.companies.length - 1) / 2) * 6}
                        cy={v.delayed > 0 ? -17.5 : -11.5}
                        fill={palette.company[code] ?? '#94a3b8'}
                        stroke="#fff" strokeWidth="0.7" />
              ))}
            </g>
            <title>{`${v.name}${v.sog != null ? ` · ${v.sog.toFixed(1)} kn` : ''}${v.destination ? ` → ${v.destination}` : ''}`
              + (v.watched ?? []).map(w => `\n• ${w.container_no}${w.reason ? ` — ${w.reason}` : ''}`).join('')}</title>
          </g>
        )
      })}
      {/* pogoda na pozostałej trasie: strzałki wiatru w punktach próbkowanych */}
      {showWeather && Object.values(weather).flatMap(w => w.route ?? []).map((p, i) => {
        if (p.wind_dir == null) return null
        const { x, y } = project(p.lat, p.lon)
        const s = view.w / WORLD_W
        return (
          <g key={`rw-${i}`} transform={`translate(${x},${y}) scale(${s})`} opacity="0.8">
            <g transform={`rotate(${(p.wind_dir + 180) % 360})`}>
              <path d="M0,7 L0,-7 M-3,-3.5 L0,-7 L3,-3.5" fill="none"
                    stroke={(p.wind_kmh ?? 0) > 50 ? '#d92d20' : '#0e8a6a'}
                    strokeWidth="1.4" strokeLinecap="round" />
            </g>
            {p.wave_m != null && (
              <text y="14" textAnchor="middle"
                    style={{ fontSize: 6, fill: '#9fd6ff', pointerEvents: 'none' }}>
                {p.wave_m} m
              </text>
            )}
          </g>
        )
      })}
      {activeVessel && replayOpen && replayPointAt(activeVessel.trail, replayIndex) && (
        <GhostMarker point={replayPointAt(activeVessel.trail, replayIndex)!} project={project} scale={view.w / WORLD_W} />
      )}
      {/* dekor makiety: terminale, magazyny, etykiety portów/krajów/statków */}
      <MapDecorOverlay view={view} showNames={showNames} showLabels={showPortLabels}
                       showAllPorts={showAllPorts} portCounts={portCounts}
                       allPortsList={containerPorts}
                       factories={factories}
                       onFactoryClick={onFactoryClick}
                       vesselLabels={showVessels
                         ? vessels.filter(v => v.lat != null && v.lon != null)
                             .map(v => ({ ...project(v.lat!, v.lon!), name: v.name }))
                         : []} />
    </svg>
  )
}
