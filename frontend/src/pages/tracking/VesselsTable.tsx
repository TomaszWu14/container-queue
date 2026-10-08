import { TriangleAlertIcon } from 'lucide-react'
import type { Dispatch, SetStateAction } from 'react'
import { formatDateTime } from '../../dates'
import { useT } from '../../i18n'
import type { Vessel } from './types'
import { WORLD_H, WORLD_W } from '../../worldmap'
import { scrollBehavior } from '../../motion'

interface Props {
  vessels: Vessel[]
  activeVessel: Vessel | null
  setActiveVessel: Dispatch<SetStateAction<Vessel | null>>
  setActive: (v: null) => void
  setPinned: (v: boolean) => void
  view: { x: number; y: number; w: number }
  setView: Dispatch<SetStateAction<{ x: number; y: number; w: number }>>
  project: (lat: number, lon: number) => { x: number; y: number }
}

/** Tabela statków AIS z kolejki — wydzielona z TrackingPage (limit 500 linii/plik). */
export default function VesselsTable({ vessels, activeVessel, setActiveVessel, setActive,
  setPinned, view, setView, project }: Props) {
  const t = useT()
  if (vessels.length === 0) return null
  return (
    <div className="panel" style={{ padding: 0, overflowX: 'auto', marginTop: 14 }}>
      <div className="panel-head" style={{ padding: '10px 14px' }}>
        <span className="mini-title" style={{ marginBottom: 0 }}>{t('aisVessels')}</span>
      </div>
      <table className="grid">
        <thead>
          <tr>
            <th>{t('vessel')}</th><th>MMSI</th><th>IMO</th><th>{t('aisPosition')}</th>
            <th>{t('aisSpeed')}</th><th>{t('aisDestination')}</th>
            <th>{t('aisEta')}</th><th>{t('aisDrift')}</th>
            <th>{t('aisHoursToDest')}</th><th>{t('aisLastSeen')}</th>
          </tr>
        </thead>
        <tbody>
          {vessels.map(v => (
            <tr key={v.id}
                className={activeVessel?.id === v.id ? 'row-active' : (v.lat != null ? 'clickable' : '')}
                style={{ cursor: v.lat != null ? 'pointer' : undefined }}
                onClick={() => {
                  if (v.lat == null) return
                  setActive(null); setPinned(false)
                  setActiveVessel(av => av?.id === v.id ? null : v)
                  const { x, y } = project(v.lat!, v.lon!)
                  const w = Math.max(WORLD_W / 8, view.w * 0.5)
                  const h = w * (WORLD_H / WORLD_W)
                  setView({ x: Math.min(Math.max(0, x - w / 2), WORLD_W - w),
                            y: Math.min(Math.max(0, y - h / 2), WORLD_H - h), w })
                  window.scrollTo({ top: 0, behavior: scrollBehavior() })
                }}>
              <td className="strong">{v.name}</td>
              <td className="mono">
                {v.mmsi
                  ? <a href={`https://www.vesselfinder.com/?mmsi=${v.mmsi}`}
                       target="_blank" rel="noreferrer">{v.mmsi}</a>
                  : <span className="muted">{t('aisLearning')}</span>}
              </td>
                  <td className="mono">
                    {v.imo
                      ? <a href={`https://www.vesselfinder.com/?imo=${v.imo}`}
                           target="_blank" rel="noreferrer">{v.imo}</a>
                      : <span className="muted">—</span>}
                  </td>
              <td className="mono">
                {v.lat != null ? `${v.lat.toFixed(2)}, ${v.lon!.toFixed(2)}` : '—'}
              </td>
              <td className="mono">{v.sog != null ? `${v.sog.toFixed(1)} kn` : '—'}</td>
              <td>{v.destination || '—'}</td>
              <td className="mono">{v.ais_eta ? formatDateTime(v.ais_eta) : '—'}</td>
              <td className="mono">
                {v.drift_days == null ? '—'
                  : <span className={v.eta_alert ? 'drift-alert' : 'muted'}>
                      {v.drift_days > 0 ? `+${v.drift_days}` : v.drift_days} {t('daysAbbrev')}
                    </span>}
              </td>
              <td className="mono">
                {v.hours_to_dest != null ? `~${Math.round(v.hours_to_dest)} h` : '—'}
                {v.predicted_late && <span className="drift-alert" title={t('predictedLateHint')}> <TriangleAlertIcon size={14} /></span>}
              </td>
              <td className="muted">{v.last_seen ? formatDateTime(v.last_seen) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
