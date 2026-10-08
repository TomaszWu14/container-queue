import { CircleCheckIcon, ClockIcon } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../api'
import { LoadError, Skeleton, useToast } from '../feedback'
import { useLocale, useT } from '../i18n'
import { useUser } from '../App'
import { Field } from '../Field'
import { useConfirm } from '../ConfirmDialog'
import { PageHeader } from '../PageHeader'
import { useVisibleInterval } from '../useVisibleInterval'

// #60: kolejka bramy — dzisiejsze spodziewane auta, duża czcionka (ochrona przy bramie),
// auto-refresh co 60 s, przycisk „Przyjechał" (check-in, idempotentny per dzień).
export interface GateItem {
  id: number
  container_no: string
  truck_no: string
  trailer_no: string
  driver_name: string
  warehouse_id: number | null
  warehouse: string
  notify_date: string | null
  eta: string | null
  status: string
  driver_arrived_at: string | null
  checked_in_at: string | null
  ramp_stage?: string | null
}

// D9: etap rampy — drugi wymiar obok statusu; „Przyjechałem" kierowcy ustawia PODSTAWIONY
const RAMP_STAGES = ['PODSTAWIONY', 'ROZLADOWANY', 'PRZYJETY']

const fmtTime = (iso: string | null, locale: string) =>
  iso ? new Date(`${iso}Z`).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }) : ''

export default function GatePage() {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const { showToast } = useToast()
  const { prompt } = useConfirm()
  const [params] = useSearchParams()
  const magazyn = params.get('magazyn') || ''
  const [items, setItems] = useState<GateItem[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(0)

  const canCheckin = user?.role === 'admin' || user?.role === 'logistics' || user?.role === 'warehouse'

  const load = useCallback(() => {
    // ?magazyn=<id> — tylko liczbowe id trafia do API (inaczej pełny zakres użytkownika)
    const q = /^\d+$/.test(magazyn) ? `?warehouse_id=${magazyn}` : ''
    api.get<{ items: GateItem[] }>(`/api/gate${q}`)
      .then(r => { setItems(r.items); setError('') })
      .catch(err => setError(errorMessage(err)))
  }, [magazyn])

  useEffect(() => { load() }, [load])
  useVisibleInterval(load, 60_000)   // auto-refresh 60 s (tylko widoczna karta)

  const checkin = async (id: number) => {
    setBusy(id)
    try {
      await api.post(`/api/gate/${id}/checkin`, {})
      showToast(t('toastSaved'))
      load()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(0) }
  }

  // kierowca zadzwonił, że się spóźni — ta sama ścieżka co dawna strona kierowcy (dzwonek, okno 30 min)
  const delay = async (id: number) => {
    const etaTime = await prompt(t('gateDelayPrompt'))
    if (!etaTime) return
    setBusy(id)
    try {
      await api.post(`/api/gate/${id}/delay`, { eta_time: etaTime })
      showToast(t('toastSaved'))
      load()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(0) }
  }

  const setRamp = async (id: number, stage: string) => {
    setBusy(id)
    try {
      await api.post(`/api/containers/${id}/ramp-stage`, { stage: stage || null })
      load()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(0) }
  }

  return (
    <main className="page gate-page">
      <PageHeader title={t('gateTitle')} subtitle={t('gateRefreshInfo')} />
      {error && !items && <LoadError message={error} onRetry={load} />}
      {error && items && <p className="error">{error}</p>}
      {!items && !error && <Skeleton rows={4} />}
      {items && items.length === 0 && <p className="muted gate-big">{t('gateNoTrucks')}</p>}
      {items && items.map(item => (
        <div key={item.id} className={`panel gate-row${item.checked_in_at ? ' gate-done' : ''}`}>
          <div className="gate-main">
            <b className="mono gate-no">{item.container_no}</b>
            {/* C29: bez numeru auta nie pokazujemy samotnego „—” */}
            {(item.truck_no || item.trailer_no) && (
              <span className="gate-truck mono">
                {item.truck_no}{item.trailer_no ? ` / ${item.trailer_no}` : ''}
              </span>
            )}
            {item.driver_name && <span className="gate-driver">{item.driver_name}</span>}
            <span className="muted">{item.warehouse}</span>
          </div>
          <div className="gate-side">
            {canCheckin
              ? <Field label={t('gateRamp')}>
                  <select value={item.ramp_stage || ''} disabled={busy === item.id}
                          onChange={e => setRamp(item.id, e.target.value)}>
                    <option value="">{t('gateRamp_none')}</option>
                    {RAMP_STAGES.map(s => <option key={s} value={s}>{t(`gateRamp_${s}`)}</option>)}
                  </select>
                </Field>
              : item.ramp_stage && <span className="muted">{t('gateRamp')}: {t(`gateRamp_${item.ramp_stage}`)}</span>}
            {item.driver_arrived_at && (
              <span className="badge st-W_DOSTAWIE">
                {t('gateDriverArrived')} {fmtTime(item.driver_arrived_at, locale)}
              </span>
            )}
            {canCheckin && !item.checked_in_at && (
              <button className="btn secondary gate-btn" disabled={busy === item.id}
                      onClick={() => delay(item.id)}>
                <ClockIcon size={14} /> {t('gateDelayBtn')}
              </button>
            )}
            {item.checked_in_at
              ? <span className="badge st-DOSTARCZONY">✓ {t('gateCheckedIn')} {fmtTime(item.checked_in_at, locale)}</span>
              : canCheckin && (
                <button className="btn gate-btn" disabled={busy === item.id}
                        onClick={() => checkin(item.id)}>
                  <CircleCheckIcon size={14} /> {t('gateArrivedBtn')}
                </button>
              )}
          </div>
        </div>
      ))}
    </main>
  )
}
