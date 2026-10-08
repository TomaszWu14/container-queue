// Publiczny formularz awizacji — ETAP 2 (dane kierowców), link wysyłany po zatwierdzeniu
// etapu 1. Mobile-first: karta per kontener. Walidacja odzwierciedla backend
// (avizo.py: _phone/_plate) — backend i tak jest źródłem prawdy (422).
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { errorMessage } from '../api'
import { useT } from '../i18n'
import { formatDate } from '../dates'
import { PublicShell, postPublic, usePublicForm, type AvizoHead } from './AvizoFormPage'

interface Stage2Item {
  container_id: number
  container_no: string
  vessel: string
  notify_date: string | null
  warehouse: string
  slot_time: string | null
}

interface Stage2Data extends AvizoHead { items: Stage2Item[] }

const FIELDS = ['driver_name', 'driver_phone', 'truck_no', 'trailer_no', 'driver_id_no'] as const
type Field = typeof FIELDS[number]
type Driver = Record<Field, string>

const EMPTY: Driver = { driver_name: '', driver_phone: '', truck_no: '', trailer_no: '', driver_id_no: '' }

const plate = (v: string) => v.replace(/[\s-]/g, '').toUpperCase()

// zwraca klucz i18n błędu albo '' — te same reguły co backend
export function driverError(field: Field, value: string): string {
  const v = value.trim()
  if (field === 'driver_name') return v.length >= 2 ? '' : 'av2ErrName'
  if (field === 'driver_phone') {
    const digits = v.replace(/[\s().-]/g, '').replace(/^00/, '+')
    return /^\d{9}$/.test(digits) || /^\+[1-9]\d{7,14}$/.test(digits) ? '' : 'av2ErrPhone'
  }
  if (field === 'truck_no') return /^[A-Z0-9]{4,10}$/.test(plate(v)) ? '' : 'av2ErrPlate'
  if (field === 'trailer_no') return !v || /^[A-Z0-9]{4,10}$/.test(plate(v)) ? '' : 'av2ErrPlate'
  return ''
}

export default function AvizoDriverFormPage({ requestId }: { requestId?: number } = {}) {
  const { token } = useParams()
  const base = requestId ? `/api/avizo-forwarder/${requestId}` : `/api/avizo/driver/${token}`
  const { state, setState, load } = usePublicForm<Stage2Data>(base)
  const lang = state.kind === 'ready' ? state.data.language : undefined
  const t = useT(lang)
  const [drivers, setDrivers] = useState<Record<number, Driver>>({})
  const [touched, setTouched] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (state.kind === 'ready')
      setDrivers(Object.fromEntries(state.data.items.map(i => [i.container_id, { ...EMPTY }])))
  }, [state])

  const labels: Record<Field, string> = {
    driver_name: t('driverName'), driver_phone: t('driverPhone'), truck_no: t('truckNo'),
    trailer_no: t('trailerNo'), driver_id_no: t('av2IdOptional'),
  }

  const submit = async (items: Stage2Item[]) => {
    setTouched(true)
    setError('')
    if (items.some(i => FIELDS.some(f => driverError(f, drivers[i.container_id]?.[f] ?? '')))) return
    setBusy(true)
    try {
      const res = await postPublic(requestId ? `${base}/drivers` : base, {
        items: items.map(i => ({ container_id: i.container_id, ...drivers[i.container_id] })),
      })
      if (res.ok || res.status === 409) setState({ kind: 'done' })
      else if (res.status === 410) setState({ kind: 'gone' })
      else setError(res.message)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <PublicShell state={state} load={load} lang={lang} title={t('av2Title')}
                 doneText={t('av2DoneInfo')}>
      {data => (
        <>
          <p className="muted">{t('av2Intro')}</p>
          {data.items.map(item => {
            const d = drivers[item.container_id]
            if (!d) return null
            return (
              <section key={item.container_id} className="panel avizo-card">
                <div className="avizo-card-head">
                  <b className="mono">{item.container_no}</b>
                  <span className="muted">
                    {[item.vessel, item.warehouse].filter(Boolean).join(' · ')}
                  </span>
                  <span className="mono">{formatDate(item.notify_date)}
                    {item.slot_time && ` ${item.slot_time}`}</span>
                </div>
                <div className="avizo-fields">
                  {FIELDS.map(f => {
                    const err = touched ? driverError(f, d[f]) : ''
                    const isPlate = f === 'truck_no' || f === 'trailer_no'
                    return (
                      <label key={f}>{labels[f]}
                        <input value={d[f]} aria-invalid={!!err || undefined}
                               type={f === 'driver_phone' ? 'tel' : 'text'}
                               inputMode={f === 'driver_phone' ? 'tel' : undefined}
                               autoComplete={f === 'driver_name' ? 'name' : f === 'driver_phone' ? 'tel' : 'off'}
                               autoCapitalize={isPlate ? 'characters' : undefined}
                               maxLength={f === 'driver_name' ? 160 : f === 'driver_id_no' ? 60 : 40}
                               onChange={e => setDrivers(all => ({
                                 ...all, [item.container_id]: { ...all[item.container_id], [f]: e.target.value },
                               }))} />
                        {err && <span className="error">{t(err)}</span>}
                      </label>
                    )
                  })}
                </div>
              </section>
            )
          })}
          <section className="panel avizo-rodo">
            <div className="mini-title">{t('av2RodoTitle')}</div>
            <p className="muted">{t('av2Rodo')}</p>
          </section>
          {error && <p className="error">{error}</p>}
          <div className="row" style={{ justifyContent: 'flex-end', marginTop: 14 }}>
            <button className="btn" disabled={busy} onClick={() => void submit(data.items)}>
              {busy ? t('loading') : t('av2Submit')}
            </button>
          </div>
        </>
      )}
    </PublicShell>
  )
}
