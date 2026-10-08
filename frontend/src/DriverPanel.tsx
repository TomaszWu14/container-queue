import { CircleXIcon, SmartphoneIcon } from 'lucide-react'
import { FormEvent, useCallback, useEffect, useState } from 'react'
import { api, errorMessage } from './api'
import { useT } from './i18n'
import type { Container } from './types'
import { formatDateTime } from './dates'
import { Field } from './Field'

// Dane kierowcy/auta na karcie kontenera + wysyłka SMS do kierowcy.
// Publiczny import zostaje przez './collaboration' (re-eksport).

export function DriverPanel({ container, onSaved, readOnly = false }: {
  container: Container
  onSaved: () => void
  readOnly?: boolean
}) {
  const t = useT()
  const [form, setForm] = useState({
    driver_name: container.driver_name, driver_id_no: container.driver_id_no,
    truck_no: container.truck_no, trailer_no: container.trailer_no,
    driver_phone: container.driver_phone,
  })
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  // blokada optymistyczna: stan kontenera z chwili wczytania formularza (nie z odświeżeń karty —
  // te nie nadpisują pól formularza, więc świeży updated_at przepuściłby nadpisanie cudzej zmiany)
  const [seenUpdatedAt, setSeenUpdatedAt] = useState(container.updated_at)
  // synchronizacja formularza po zmianie kontenera — inaczej zapis wysłałby dane poprzedniego
  useEffect(() => {
    setForm({
      driver_name: container.driver_name, driver_id_no: container.driver_id_no,
      truck_no: container.truck_no, trailer_no: container.trailer_no,
      driver_phone: container.driver_phone,
    })
    setSeenUpdatedAt(container.updated_at)
    setSaved(false)
  }, [container.id])

  const save = async (event: FormEvent) => {
    event.preventDefault()
    if (saving) return
    setError('')
    setSaved(false)
    setSaving(true)
    try {
      const out = await api.patch<Container>(`/api/containers/${container.id}/driver`,
        { ...form, expected_updated_at: seenUpdatedAt })
      setSeenUpdatedAt(out.updated_at)
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const fields: [keyof typeof form, string][] = [
    ['driver_name', t('driverName')], ['driver_id_no', t('driverId')],
    ['truck_no', t('truckNo')], ['trailer_no', t('trailerNo')],
    ['driver_phone', t('driverPhone')],
  ]

  if (readOnly) {
    return (
      <div className="panel">
        <h3>{t('driverData')}</h3>
        <div className="row" style={{ gap: 24 }}>
          {fields.map(([key, label]) => (
            <span key={key} style={{ fontSize: 14 }}>
              <b style={{ color: 'var(--muted)', fontSize: 12, display: 'block',
                          textTransform: 'uppercase' }}>{label}</b>
              {container[key] || '—'}
            </span>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="panel">
      <h3>{t('driverData')}</h3>
      {/* A29/C33: etykieta nad polem — placeholder znikał po wpisaniu i ucinał „Imię i nazwisko…” */}
      <form className="field-row" onSubmit={save}>
        {fields.map(([key, label]) => (
          <Field key={key} label={label} className={key === 'driver_name' ? 'wide' : undefined}>
            <input value={form[key]}
                   inputMode={key === 'driver_phone' ? 'tel' : undefined}
                   autoCapitalize={key === 'truck_no' || key === 'trailer_no' ? 'characters' : undefined}
                   onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
          </Field>
        ))}
        <button className="btn secondary" disabled={saving}>{t('save')}</button>
        {saved && <span className="field-row-ok">✓</span>}
      </form>
      {error && <p className="error">{error}</p>}
      <DriverSmsRow container={container} />
    </div>
  )
}

function DriverSmsRow({ container }: { container: Container }) {
  const t = useT()
  const [history, setHistory] = useState<{ configured: boolean
    messages: { id: number; phone: string; status: string; error: string; created_at: string }[] } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.get<NonNullable<typeof history>>(`/api/containers/${container.id}/driver-sms`)
      .then(setHistory).catch(() => {})
  }, [container.id])
  useEffect(() => load(), [load])

  const send = async () => {
    setBusy(true); setError('')
    try {
      await api.post(`/api/containers/${container.id}/driver-sms`, {})
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (!history?.configured && !history?.messages.length) return null
  const last = history?.messages[0]
  return (
    <div className="row" style={{ marginTop: 10, gap: 10, alignItems: 'center' }}>
      {history?.configured && (
        <button className="btn small secondary" disabled={busy || !container.driver_phone}
                onClick={send}>
          <SmartphoneIcon size={14} /> {t('sendDriverSms')}
        </button>
      )}
      {last && (
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>
          {t('lastSms')}: {formatDateTime(last.created_at)} → {last.phone}{' '}
          {last.status === 'sent'
            ? <span style={{ color: '#0e8a6a', fontWeight: 700 }}>✓</span>
            : <span style={{ color: 'var(--danger)' }} title={last.error}><CircleXIcon size={14} /> {last.error}</span>}
        </span>
      )}
      {error && <span className="error" style={{ margin: 0 }}>{error}</span>}
    </div>
  )
}
