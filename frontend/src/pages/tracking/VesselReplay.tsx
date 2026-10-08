import { PlayIcon } from 'lucide-react'
import { useState } from 'react'
import { useT } from '../../i18n'
import type { Vessel } from './types'

/** Stan slidera replay — wspólny dla przycisku w tooltipie i markera-ducha na mapie. */
export function useVesselReplay() {
  const [open, setOpen] = useState(false)
  const [index, setIndex] = useState(0)
  return { open, setOpen, index, setIndex }
}

interface ControlsProps {
  vessel: Vessel
  open: boolean
  setOpen: (v: boolean) => void
  index: number
  setIndex: (v: number) => void
}

/** Przycisk „▶ Replay" + suwak po trasie statku — do wnętrza tooltipa (#38). */
export function ReplayControls({ vessel, open, setOpen, index, setIndex }: ControlsProps) {
  const t = useT()
  if (vessel.trail.length < 2) return null
  return (
    <div style={{ marginTop: 6 }}>
      <button className="btn small secondary" onClick={() => setOpen(!open)}>
        <PlayIcon size={14} /> {t('replay')}
      </button>
      {open && (
        <input aria-label={t('replay')} type="range" min={0} max={vessel.trail.length - 1} value={index}
               onChange={e => setIndex(Number(e.target.value))}
               style={{ width: '100%', marginTop: 6 }} />
      )}
    </div>
  )
}

interface GhostProps {
  point: [number, number]
  project: (lat: number, lon: number) => { x: number; y: number }
  scale: number
}

/** Marker-duch trasy przy replayu — bez animacji, tylko pozycja z suwaka. */
export function GhostMarker({ point, project, scale }: GhostProps) {
  const { x, y } = project(point[0], point[1])
  return (
    <g transform={`translate(${x},${y}) scale(${scale})`} opacity="0.8">
      <circle r="5" fill="none" stroke="#f5a623" strokeWidth="1.6" strokeDasharray="2 1.5" />
      <circle r="1.6" fill="#f5a623" />
    </g>
  )
}
