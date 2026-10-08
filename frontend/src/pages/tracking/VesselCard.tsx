import { AnchorIcon, ChevronDownIcon, ChevronRightIcon, FlagIcon, PackageIcon, ShipIcon, StarIcon, TriangleAlertIcon, WavesIcon, WindIcon, XIcon } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api, errorMessage } from '../../api'
import { formatDate, formatDateTime } from '../../dates'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import WatchersPanel from '../watch/WatchersPanel'
import type { CargoContainer, Vessel, VesselCargo } from './types'

/** Sylwetka kontenerowca — placeholder, gdy statek nie ma zdjęcia. */
export function VesselPlaceholder() {
  return (
    <svg viewBox="0 0 320 120" className="vessel-photo placeholder" aria-hidden
         preserveAspectRatio="xMidYMid slice">
      <rect width="320" height="120" fill="#0c2846" />
      <rect y="88" width="320" height="32" fill="#123a63" />
      {/* kadłub */}
      <path d="M28 78 L292 78 L272 100 L52 100 Z" fill="#22415f" />
      {/* nadbudówka */}
      <rect x="236" y="46" width="26" height="32" fill="#3a5c7e" />
      <rect x="240" y="40" width="18" height="6" fill="#4a6c8e" />
      {/* kontenery */}
      {[0, 1, 2].map(r => [0, 1, 2, 3, 4, 5].map(c => (
        <rect key={`${r}-${c}`} x={56 + c * 29} y={70 - r * 9} width="26" height="8"
              fill={['#2f8ef7', '#f5a623', '#0e8a6a', '#d99e00'][(r + c) % 4]} opacity="0.75" />
      )))}
      {/* fala */}
      <path d="M0 100 Q40 94 80 100 T160 100 T240 100 T320 100 V120 H0 Z"
            fill="#0a1e36" opacity="0.8" />
    </svg>
  )
}

function Param({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="vc-param">
      <span className="vc-label">{label}</span>
      <span className="vc-value">{children ?? '—'}</span>
    </div>
  )
}

interface Props {
  vessel: Vessel
  companyColor: Record<string, string>
  weather?: { wind_kmh: number | null; wave_m: number | null }
  canEdit: boolean       // admin/logistics: flaga „specjalny"
  isAdmin: boolean       // upload/auto-fetch zdjęcia
  onClose: () => void
  onOpenContainer: (id: number) => void
  children?: ReactNode   // ReplayControls z TrackingPage
}

/** Karta statku — rozbudowany panel po kliknięciu statku (2D i globus). */
export default function VesselCard({ vessel, companyColor, weather, canEdit, isAdmin,
  onClose, onOpenContainer, children }: Props) {
  const t = useT()
  const { showToast } = useToast()
  const [photoRev, setPhotoRev] = useState(0)          // cache-bust po uploadzie
  const [hasPhoto, setHasPhoto] = useState(vessel.has_photo)
  const [fetching, setFetching] = useState(false)
  const [cargoOpen, setCargoOpen] = useState(false)
  const [cargo, setCargo] = useState<VesselCargo | null>(null)
  const [cargoError, setCargoError] = useState('')
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const fileRef = useRef<HTMLInputElement>(null)
  useEffect(() => {   // zmiana statku = świeża karta
    setHasPhoto(vessel.has_photo); setCargo(null); setCargoOpen(false)
    setExpanded(new Set()); setCargoError('')
  }, [vessel.id, vessel.has_photo])

  const loadCargo = () => {
    setCargoOpen(o => !o)
    if (cargo) return
    api.get<VesselCargo>(`/api/tracking/vessels/${vessel.id}/cargo`)
      .then(setCargo)
      .catch(err => setCargoError(errorMessage(err)))
  }

  const toggleSpecial = async (c: CargoContainer) => {
    try {
      const res = await api.post<{ is_special: boolean }>(`/api/containers/${c.id}/special`, { is_special: !c.is_special })
      setCargo(cur => cur && {
        ...cur,
        containers: cur.containers.map(x => x.id === c.id ? { ...x, is_special: res.is_special } : x),
      })
      showToast(res.is_special ? t('specialOn') : t('specialOff'), 'success')
    } catch (err) {
      showToast(errorMessage(err), 'error')
    }
  }

  const uploadPhoto = async (file: File) => {
    try {
      await api.upload(`/api/tracking/vessels/${vessel.id}/photo`, file)
      setHasPhoto(true); setPhotoRev(r => r + 1)
      showToast(t('vcPhotoSaved'), 'success')
    } catch (err) {
      showToast(errorMessage(err), 'error')
    }
  }

  const autoFetch = async () => {
    setFetching(true)
    try {
      await api.post(`/api/tracking/vessels/${vessel.id}/photo/fetch`, {})
      setHasPhoto(true); setPhotoRev(r => r + 1)
      showToast(t('vcPhotoSaved'), 'success')
    } catch (err) {
      showToast(errorMessage(err), 'error')
    } finally {
      setFetching(false)
    }
  }

  return (
    <div role="dialog" aria-label={vessel.name} className="map-tooltip pinned vessel-card">
      <button className="map-tooltip-close" aria-label={t('close')} onClick={onClose}><XIcon size={14} /></button>
      {hasPhoto
        ? <img className="vessel-photo" alt={vessel.name} width={340} height={120} loading="lazy"
               src={`/api/tracking/vessels/${vessel.id}/photo?r=${photoRev}`}
               onError={() => setHasPhoto(false)} />
        : <VesselPlaceholder />}
      {isAdmin && (
        <div className="row vc-photo-actions">
          <button className="btn small secondary" onClick={() => fileRef.current?.click()}>
            {t('vcPhotoUpload')}
          </button>
          <button className="btn small secondary" disabled={fetching || !vessel.imo}
                  title={vessel.imo ? undefined : t('vcPhotoNeedsImo')} onClick={autoFetch}>
            {fetching ? '…' : t('vcPhotoAuto')}
          </button>
          <input ref={fileRef} type="file" accept="image/*" hidden
                 onChange={e => { const f = e.target.files?.[0]; if (f) uploadPhoto(f); e.target.value = '' }} />
        </div>
      )}
      <b><ShipIcon size={14} /> {vessel.name}</b>
      <span style={{ marginLeft: 6 }}>
        {vessel.companies.map(code => (
          <span key={code} className="badge" style={{
            background: companyColor[code] ?? '#94a3b8', color: '#fff', marginRight: 4 }}>
            {code}
          </span>
        ))}
      </span>

      <div className="vc-grid">
        <Param label="IMO">{vessel.imo ?? '—'}</Param>
        <Param label="MMSI">{vessel.mmsi ?? '—'}</Param>
        <Param label={t('vcDims')}>
          {vessel.length_m ? `${vessel.length_m} × ${vessel.beam_m ?? '?'} m` : '—'}
        </Param>
        <Param label={t('aisSpeed')}>
          {vessel.sog != null ? `${vessel.sog.toFixed(1)} kn` : '—'}
          {vessel.cog != null && ` · ${Math.round(vessel.cog)}°`}
        </Param>
        <Param label={t('aisDestination')}>{vessel.destination || '—'}</Param>
        <Param label={t('aisEta')}>
          {vessel.ais_eta ? formatDateTime(vessel.ais_eta) : '—'}
        </Param>
        <Param label={t('aisPosition')}>
          {vessel.lat != null ? `${vessel.lat.toFixed(2)}, ${vessel.lon!.toFixed(2)}` : '—'}
        </Param>
        <Param label={t('aisLastSeen')}>
          {vessel.last_seen ? formatDateTime(vessel.last_seen) : '—'}
        </Param>
      </div>
      <WatchersPanel baseUrl={`/api/tracking/vessels/${vessel.id}`} framed={false} />
      {(vessel.watched?.length ?? 0) > 0 && (
        <div className="vessel-watched">
          <b className="watch-mark"><StarIcon size={14} fill="currentColor" aria-hidden="true" /> {t('watchedAboard')}</b>
          <ul className="vessel-watched-list">
            {vessel.watched!.map(w => (
              <li key={w.id}><span className="mono">{w.container_no}</span>
                {w.reason && <> — <span className="watcher-reason">{w.reason}</span></>}</li>
            ))}
          </ul>
        </div>
      )}
      {weather?.wind_kmh != null && (
        <div className="muted" style={{ fontSize: 13 }}>
          <WindIcon size={14} /> {Math.round(weather.wind_kmh)} km/h
          {weather.wave_m != null && <> · <WavesIcon size={12} /> {weather.wave_m} m</>}
        </div>
      )}
      {vessel.hours_to_dest != null && (
        <div>{t('aisHoursToDest')}: ~{Math.round(vessel.hours_to_dest)} h</div>
      )}
      {vessel.near_port && <div><AnchorIcon size={14} /> {vessel.near_port}</div>}
      {vessel.predicted_late && <div className="drift-alert"><TriangleAlertIcon size={14} /> {t('predictedLateHint')}</div>}
      {vessel.eta_alert && (
        <div className="drift-alert"><TriangleAlertIcon size={14} /> {t('aisDriftWarn')} +{vessel.drift_days} {t('daysAbbrev')}</div>
      )}

      {/* nasze kontenery: licznik + rozwijana lista + akordeon zawartości */}
      <button className="vc-cargo-toggle" aria-expanded={cargoOpen} onClick={loadCargo}>
        <PackageIcon size={14} /> {vessel.containers} {t('contAbbrev')}
        {vessel.delayed > 0 && (
          <b style={{ color: 'var(--danger)' }}> · {vessel.delayed} {t('lateAbbrev')}</b>
        )}
        <span className="vc-chevron">{cargoOpen ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}</span>
      </button>
      {cargoOpen && (
        <div className="vc-cargo">
          {cargoError && <p className="error">{cargoError}</p>}
          {!cargo && !cargoError && <span className="muted">…</span>}
          {cargo?.containers.map(c => (
            <div key={c.id} className="vc-container">
              <div className="row vc-container-head">
                {canEdit && (
                  <button type="button"
                          className={`watch-star${c.is_special ? ' on' : ''}`}
                          title={t('specialToggle')}
                          onClick={() => toggleSpecial(c)}><FlagIcon size={14} /></button>
                )}
                {!canEdit && c.is_special && <span title={t('specialFlag')}><FlagIcon size={14} /></span>}
                <a className="mono strong link-like"
                   onClick={() => onOpenContainer(c.id)}>{c.container_no}</a>
                <span className="badge" style={{
                  background: companyColor[c.company] ?? '#94a3b8', color: '#fff' }}>
                  {c.company}
                </span>
                <span className={`badge st-${c.status}`}>{t(`st_${c.status}`)}</span>
                {c.eta && <span className="mono muted">{formatDate(c.eta)}</span>}
                {cargo.items_visible && c.items.length > 0 && (
                  <button className="vc-items-toggle" aria-expanded={expanded.has(c.id)}
                          onClick={() => setExpanded(cur => {
                            const next = new Set(cur)
                            if (next.has(c.id)) next.delete(c.id); else next.add(c.id)
                            return next
                          })}>
                    {expanded.has(c.id) ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />} {t('vcContents')}
                  </button>
                )}
              </div>
              {expanded.has(c.id) && (
                <table className="vc-items">
                  <thead>
                    <tr><th>{t('mdMaterialNo')}</th><th>{t('refDesc')}</th>
                        <th>{t('refQty')}</th></tr>
                  </thead>
                  <tbody>
                    {c.items.map((i, k) => (
                      <tr key={k}>
                        <td className="mono">{i.material}</td>
                        <td>{i.description}</td>
                        <td className="mono">{i.quantity} {i.unit}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {expanded.has(c.id) && c.items.length === 0 && (
                <span className="muted">{t('vcNoItems')}</span>
              )}
            </div>
          ))}
          {cargo && cargo.containers.length === 0 && (
            <span className="muted">{t('vcNoContainers')}</span>
          )}
        </div>
      )}
      {children}
    </div>
  )
}
