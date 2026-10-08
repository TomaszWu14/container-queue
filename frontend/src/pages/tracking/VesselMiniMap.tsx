import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api'
import { useT } from '../../i18n'
import { WORLD_H, WORLD_W } from '../../worldmap'
import { LAND_PATH } from './mapStatic'
import { splitTrailSegments } from './mapUtils'
import type { Vessel } from './types'
import VesselIcon from './VesselIcon'

const project = (lat: number, lon: number) => ({
  x: (lon + 180) / 360 * WORLD_W,
  y: (90 - lat) / 180 * WORLD_H,
})

// Minimalny kształt danych mapki — pozycja + trasa, bez nazw/metadanych
// (publiczny endpoint portalu zwraca dokładnie tyle).
export type MiniMapData = { lat: number; lon: number; cog?: number | null; trail: [number, number][] }

/** Prezentacyjna mini-mapa: pozycja + trail. Wspólna dla karty kontenera i portalu. */
export function MiniMapSvg({ data, onClick, label }:
  { data: MiniMapData; onClick?: () => void; label?: string }) {
  const { x, y } = project(data.lat, data.lon)
  // K3: trasa przez antymerydian dzielona na segmenty — jak na pełnej mapie
  const trailSegments = splitTrailSegments<[number, number]>([...data.trail, [data.lat, data.lon]])
    .map(seg => seg.map(([la, lo]) => project(la, lo)))

  return (
    <svg viewBox={`0 0 ${WORLD_W} ${WORLD_H}`} height={180}
         style={{ width: '100%', cursor: onClick ? 'pointer' : 'default' }}
         role={onClick ? 'button' : 'img'} aria-label={label}
         onClick={onClick}>
      {/* clip do viewBoxa: LAND_PATH ma kopie ringów przesunięte o szerokość świata
          (antymerydian), a svg o stałej wysokości renderuje też poza viewBox */}
      <defs><clipPath id="mm-clip"><rect width={WORLD_W} height={WORLD_H} /></clipPath></defs>
      <rect width={WORLD_W} height={WORLD_H} fill="#0d1f36" />
      <path d={LAND_PATH} fill="#24425f" stroke="#3a5c7e" strokeWidth="0.5" clipPath="url(#mm-clip)" />
      {trailSegments.map((seg, i) => seg.length > 1 && (
        <polyline key={i} points={seg.map(p => `${p.x},${p.y}`).join(' ')}
                  fill="none" stroke="#f5a623" strokeWidth="2" strokeDasharray="4 3" strokeOpacity="0.85" />
      ))}
      <g transform={`translate(${x},${y}) rotate(${data.cog ?? 0})`}>
        <VesselIcon />
      </g>
    </svg>
  )
}

/** Mini-mapa AIS na karcie kontenera (#37) — pozycja + trasa statku, klik → pełny widok. */
export default function VesselMiniMap({ vesselName }: { vesselName: string }) {
  const t = useT()
  const navigate = useNavigate()
  const [vessel, setVessel] = useState<Vessel | null>(null)

  useEffect(() => {
    let alive = true
    const norm = vesselName.trim().toUpperCase()
    api.get<Vessel[]>('/api/tracking/vessels').then(list => {
      if (!alive || !Array.isArray(list)) return
      setVessel(list.find(v => v.name.trim().toUpperCase() === norm) ?? null)
    }).catch(() => {})
    return () => { alive = false }
  }, [vesselName])

  if (!vessel || vessel.lat == null || vessel.lon == null) return null
  return (
    <MiniMapSvg data={{ lat: vessel.lat, lon: vessel.lon, cog: vessel.cog, trail: vessel.trail }}
                onClick={() => navigate('/sledzenie')} label={t('miniMapOpenHint')} />
  )
}
