import { PlayIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import QRCode from 'qrcode'
import { api, errorMessage } from '../api'
import { LoadError, Skeleton, useToast } from '../feedback'
import { useT } from '../i18n'
import type { Container } from '../types'
import { formatDate } from '../dates'
import { ChecklistPanel } from './ChecklistPanel'
import { useUser } from '../userContext'

// #46: drukowalna karta rozładunku (/kontenery/:id/karta). QR koduje link do
// ContainerPage — magazyn skanuje i trafia od razu na kontener.
// Zależność: pakiet npm 'qrcode' (generuje dataURL, brak wywołań sieciowych/zewnętrznych).
// #61 Start/Stop pomiaru czasu rozładunku, #62 drukowalna etykieta QR,
// #64 zdjęcia z rozładunku + reklamacja z prefillu.
type Palletization =
  | { configured: false }
  | { configured: true; data: unknown }
  | { configured: true; error: string }

interface UnloadPhoto {
  id: number
  filename: string
  caption: string
  created_at: string
}

export function durationMinutes(start?: string | null, stop?: string | null): number | null {
  if (!start || !stop) return null
  const ms = new Date(`${stop}Z`).getTime() - new Date(`${start}Z`).getTime()
  return ms >= 0 ? Math.round(ms / 60_000) : null
}

export default function KartaRozladunkuPage() {
  const { id } = useParams()
  const t = useT()
  const navigate = useNavigate()
  const { showToast } = useToast()
  // Start/Stop, zdjęcia, reklamacja i checklista: backend WarehouseOrEditors — pozostali
  // (spedytor, agencja, zakupy) widzą kartę tylko do odczytu zamiast przycisków dających 403
  const role = useUser()?.role
  const canWork = role === 'admin' || role === 'logistics' || role === 'warehouse'
  const [container, setContainer] = useState<Container | null>(null)
  const [qr, setQr] = useState('')
  const [pallet, setPallet] = useState<Palletization | null>(null)
  const [photos, setPhotos] = useState<UnloadPhoto[]>([])
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = () => {
    setLoadError('')
    api.get<Container>(`/api/containers/${id}`)
      .then(c => {
        setContainer(c)
        return QRCode.toDataURL(`${window.location.origin}/kontenery/${c.id}`)
      })
      .then(setQr)
      .catch(err => setLoadError(errorMessage(err)))
    api.get<Palletization>(`/api/containers/${id}/palletization`)
      .then(setPallet).catch(() => setPallet({ configured: false }))
    api.get<UnloadPhoto[]>(`/api/containers/${id}/unload-photos`)
      .then(setPhotos).catch(() => setPhotos([]))
  }
  useEffect(load, [id])

  if (loadError) return <main className="page"><LoadError message={loadError} onRetry={load} /></main>
  if (!container) return <main className="page"><Skeleton rows={6} /></main>

  const row = (label: string, value: React.ReactNode) => (
    <div className="item"><b>{label}</b>{value === null || value === undefined || value === '' ? '—' : value}</div>
  )

  const unload = async (action: 'start' | 'stop') => {
    setBusy(true); setError('')
    try {
      await api.post(`/api/containers/${id}/unload/${action}`, {})
      showToast(t('toastSaved'))
      load()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  const uploadPhoto = async (file: File) => {
    setBusy(true); setError('')
    try {
      await api.upload(`/api/containers/${id}/unload-photos`, file)
      showToast(t('toastSaved'))
      load()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  const makeComplaint = async (photoId: number) => {
    setBusy(true); setError('')
    try {
      const r = await api.post<{ complaint_id: number; number: string }>(
        `/api/unload-photos/${photoId}/complaint`, {})
      showToast(`${t('ulComplaintCreated')}: ${r.number}`)
      navigate(`/reklamacje/${r.complaint_id}`)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  // #62: druk etykiety QR — klasa na <body> zostawia w druku tylko .qr-label (CSS print)
  const printQrLabel = () => {
    document.body.classList.add('print-qr-label')
    window.print()
    document.body.classList.remove('print-qr-label')
  }

  const running = !!container.unload_started_at && !container.unload_finished_at
  const minutes = durationMinutes(container.unload_started_at, container.unload_finished_at)

  return (
    <main className="page unload-card">
      <div className="panel unload-card-sheet">
        <div className="unload-card-head">
          <h1 className="mono">{container.container_no}</h1>
          {qr && <img src={qr} alt="QR" width={120} height={120} loading="lazy" />}
        </div>
        <div className="detail-grid">
          {row(t('supplier'), container.supplier_name)}
          {row(t('vessel'), container.vessel)}
          {row(t('eta'), container.eta && formatDate(container.eta))}
          {row(t('notifyDate'), container.notify_date && formatDate(container.notify_date))}
          {row(t('warehouse'), container.warehouse_name)}
          {row('Palety', container.pallet_count)}
          {row(t('notes'), container.notes)}
          {minutes != null && row(t('ulDuration'), `${minutes} ${t('ulMin')}`)}
        </div>
        <ChecklistPanel containerId={container.id} editable={canWork} />
        <section>
          <h3>{t('palletization')}</h3>
          {!pallet || !pallet.configured
            ? <p className="muted">{t('palletApiNotConfigured')}</p>
            : 'error' in pallet
              ? <p className="muted">{t('palletApiError')}</p>
              : <pre className="mono" style={{ whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(pallet.data, null, 2)}
                </pre>}
        </section>
        <section className="no-print">
          <h3>{t('ulPhotos')}</h3>
          {photos.length === 0 && <p className="muted">—</p>}
          {photos.map(p => (
            <div key={p.id} className="row" style={{ gap: 10, alignItems: 'center', marginBottom: 8 }}>
              <a href={`/api/unload-photos/${p.id}/download`} target="_blank" rel="noreferrer">
                <img src={`/api/unload-photos/${p.id}/download`} alt={p.filename}
                     width={120} height={90} loading="lazy" decoding="async"
                     style={{ objectFit: 'contain', borderRadius: 6 }} />
              </a>
              <span className="muted">{p.filename}</span>
              {canWork && <button className="btn small secondary" disabled={busy}
                      onClick={() => makeComplaint(p.id)}>{t('ulMakeComplaint')}</button>}
            </div>
          ))}
          {canWork && <label className="btn small secondary">{t('ulAddPhoto')}
            <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden
                   onChange={e => {
                     const f = e.target.files?.[0]
                     if (f) void uploadPhoto(f)
                     e.target.value = ''
                   }} />
          </label>}
        </section>
      </div>
      {error && <p className="error no-print">{error}</p>}
      <div className="row no-print" style={{ gap: 8, flexWrap: 'wrap' }}>
        <button className="btn" onClick={() => window.print()}>{t('printBtn')}</button>
        <button className="btn secondary" onClick={printQrLabel}>{t('qrPrintLabel')}</button>
        {canWork && (running
          ? <button className="btn danger" disabled={busy} onClick={() => unload('stop')}>
              ⏹ {t('ulStop')}</button>
          : <button className="btn" disabled={busy || !!container.unload_finished_at}
                    onClick={() => unload('start')}>
              <PlayIcon size={14} /> {t('ulStart')}</button>)}
        {running && <span className="badge st-W_DOSTAWIE">{t('ulInProgress')}</span>}
      </div>
      {/* etykieta QR do druku — widoczna wyłącznie w trybie print-qr-label */}
      <div className="qr-label">
        {qr && <img src={qr} alt="QR" width={220} height={220} loading="lazy" />}
        <div className="mono qr-label-no">{container.container_no}</div>
        <div>{container.warehouse_name || ''}</div>
      </div>
    </main>
  )
}
