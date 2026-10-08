import { FactoryIcon, FlagIcon, ShipIcon, TriangleAlertIcon, XIcon } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { formatDate, formatDateTime } from '../../dates'
import { useT } from '../../i18n'
import type { FactoryCluster } from './MapDecor'
import type { KEY_PORTS } from './mapStatic'
import { CONTAINER_STATUSES } from '../../types/core'
import type { MapData, MapPoint, PortCongestion } from './trackingModel'

// Elementy strony trackingu wokół mapy: chipy portów, dymki (punkt/fabryka),
// legenda statusów i tabela kontenerów — wydzielone z TrackingPage.

/** Chipy kluczowych portów (makieta .chips): statki na redzie + kontenery w porcie; klik = zoom. */
export function PortChips({ chipPorts, portAnchored, portCounts, congestion, onZoom }: {
  chipPorts: typeof KEY_PORTS
  portAnchored: Map<string, number>
  portCounts: Map<string, number>
  congestion: PortCongestion[]
  onZoom: (lat: number, lon: number) => void
}) {
  const t = useT()
  if (chipPorts.length === 0) return null
  return (
    <div className="row" style={{ gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
      {chipPorts.map(p => {
        const anch = portAnchored.get(p.id) ?? 0
        const cnt = portCounts.get(p.id) ?? 0
        // trend kongestii: wiersz PortCongestion dopasowany po nazwie AIS portu
        const trend = congestion.find(c => p.ais.includes(c.port))
        const maxW = trend ? Math.max(1, ...trend.days.map(d => d.waiting)) : 1
        return (
          <button key={p.id} className="port-chip" onClick={() => onZoom(p.lat, p.lon)}
                  title={trend?.alert ? t('congestionAlertHint') : undefined}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#3f6ea8"
                 strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <circle cx="12" cy="4.5" r="2" /><path d="M12 6.5V21M6 12H18M5 15a7 7 0 0 0 14 0" />
            </svg>
            <span className="nm">{p.name.toUpperCase()}:</span>
            {anch > 0 && <><b className="mono">{anch}</b><span className="u">{t('congestionWaiting')}</span></>}
            {cnt > 0 && <span className="u">{anch > 0 ? '· ' : ''}{cnt} {t('contAbbrev')}</span>}
            {trend && trend.days.length > 1 && (
              // mini-trend kongestii 14 dni (słupki); ostatni słupek = dziś
              <svg width={trend.days.length * 3} height="12" aria-hidden
                   style={{ marginLeft: 4 }}>
                {trend.days.map((d, i) => {
                  const h = Math.max(2, Math.round(d.waiting / maxW * 12))
                  return <rect key={d.day} x={i * 3} y={12 - h} width="2" height={h}
                               fill={trend.alert && i === trend.days.length - 1
                                 ? '#d92d20' : '#3f6ea8'} />
                })}
              </svg>
            )}
            {trend?.alert && <span aria-hidden style={{ color: '#d92d20' }}><TriangleAlertIcon size={14} /></span>}
          </button>
        )
      })}
    </div>
  )
}

/** Dymek klastra fabryk dostawców (wiele firm w jednym miejscu). */
export function FactoryPopup({ factory, onClose }: { factory: FactoryCluster; onClose: () => void }) {
  const t = useT()
  const navigate = useNavigate()
  return (
    <div role="status" className="map-tooltip pinned">
      <button className="map-tooltip-close" aria-label={t('close')}
              onClick={onClose}><XIcon size={14} /></button>
      <b><FactoryIcon size={14} /> {factory.city ?? t('mapSuppliers')}</b>
      <div style={{ maxHeight: 220, overflowY: 'auto', marginTop: 4 }}>
        {factory.suppliers.map(su => (
          <div key={su.id}>
            <a style={{ color: '#9fd6ff', cursor: 'pointer' }}
               onClick={() => navigate(`/dostawcy/${su.id}`)}>{su.name}</a>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Dymek aktywnego punktu kontenera (hover = podgląd, tap/Enter = przypięty). */
export function PointTooltip({ active, pinned, clusterSize, onClose }: {
  active: MapPoint
  pinned: boolean
  clusterSize: number
  onClose: () => void
}) {
  const t = useT()
  const navigate = useNavigate()
  return (
    <div id="map-active-tooltip" role="status"
         className={'map-tooltip' + (pinned ? ' pinned' : '')}>
      {pinned && (
        <button className="map-tooltip-close" aria-label={t('close')}
                onClick={onClose}><XIcon size={14} /></button>
      )}
      <b className="mono">{active.is_special && <span title={t('specialFlag')}><FlagIcon size={14} /> </span>}{active.container_no}</b>
      {clusterSize > 1 && <span className="muted"> +{clusterSize - 1}</span>}
      <div>{active.location} — {active.event}</div>
      {active.vessel && <div><ShipIcon size={14} /> {active.vessel}</div>}
      <div>ETD: {formatDate(active.etd)} · ETA: {formatDate(active.eta)}</div>
      <div style={{ marginTop: 4 }}>
        <span className={`badge st-${active.status}`}>{t(`st_${active.status}`)}</span>
      </div>
      <button className="btn small" style={{ marginTop: 8 }}
              onClick={() => navigate(`/kontenery/${active.id}`)}>
        {t('trackOpenContainer')} →
      </button>
    </div>
  )
}

/** Etykieta statusu bez numeru etapu procesu („4 · Port docelowy" → „Port docelowy"): kilka statusów
 *  należy do tego samego etapu, więc w legendzie numery się dublowały (audyt UI C30). */
const stageLabel = (label: string) => label.replace(/^\d+\s*·\s*/, '')

/** Legenda statusów pod mapą + licznik śledzonych. */
export function StatusLegend({ data }: { data: MapData | null }) {
  const t = useT()
  return (
    <div className="map-legend">
      {/* zrealizowane nie trafiają na mapę (tracking.py). Kropka .theme-dark = ten sam kolor co na
          (zawsze ciemnej) mapie; obwódka w motywie strony — żeby jasna kropka nie ginęła na jasnym tle */}
      {CONTAINER_STATUSES.filter(s => s !== 'ZREALIZOWANY').map(status => (
        <span key={status} className="row" style={{ gap: 6 }}>
          <span style={{ display: 'inline-flex', padding: 1, borderRadius: 6, background: `var(--st-${status}-ink)` }}>
            <span className="theme-dark" style={{ width: 10, height: 10, borderRadius: 5,
              background: `var(--st-${status}-ink)`, display: 'inline-block' }} />
          </span>
          {stageLabel(t(`st_${status}`))}
        </span>
      ))}
      {data && (
        <span style={{ marginLeft: 'auto', color: 'var(--muted)' }}>
          {t('mapTracked')}: {data.tracked} / {data.total}
        </span>
      )}
    </div>
  )
}

/** Tabela kontenerów (z pozycją i bez) pod mapą; klik = karta kontenera. */
export function TrackedContainersTable({ data }: { data: MapData }) {
  const t = useT()
  const navigate = useNavigate()
  return (
    <div className="panel" style={{ padding: 0, overflowX: 'auto', marginTop: 14 }}>
      <table className="grid">
        <thead>
          <tr>
            <th>{t('containerNo')}</th><th>{t('vessel')}</th>
            <th>{t('mapLastLocation')}</th><th>ETD</th><th>{t('eta')}</th>
            <th>{t('status')}</th><th>{t('when')}</th>
          </tr>
        </thead>
        <tbody>
          {[...data.points, ...data.unlocated].map(point => (
            <tr key={point.id} className="clickable"
                onClick={() => navigate(`/kontenery/${point.id}`)}
                style={{ cursor: 'pointer' }}>
              <td className="mono strong">{point.container_no}</td>
              <td>{point.vessel}</td>
              <td>{point.location} {point.event && <span className="muted">({point.event})</span>}</td>
              <td className="mono">{point.etd ? formatDate(point.etd) : ''}</td>
              <td className="mono">{point.eta ? formatDate(point.eta) : ''}</td>
              <td><span className={`badge st-${point.status}`}>{t(`st_${point.status}`)}</span></td>
              <td className="muted">{formatDateTime(point.occurred_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
