// Spedytor z kontem proponuje inny termin dostawy kontenera z awizacji (POST …/propose) —
// ta sama reguła co dawny link: data nie z przeszłości, godzina w oknach magazynu (walidacja serwera).
import { FormEvent, useState } from 'react'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'

export function AvizoProposeForm({ requestId, items, onDone }: {
  requestId: number
  items: { container_id: number; container_no: string }[]
  onDone: () => void
}) {
  const t = useT()
  const [containerId, setContainerId] = useState(String(items[0]?.container_id ?? ''))
  const [date, setDate] = useState('')
  const [time, setTime] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.post(`/api/avizo-forwarder/${requestId}/propose`,
        { container_id: Number(containerId), date, time, note })
      onDone()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <label>{t('myAvizosContainers')}
        <select value={containerId} onChange={e => setContainerId(e.target.value)}>
          {items.map(i => <option key={i.container_id} value={i.container_id}>{i.container_no}</option>)}
        </select>
      </label>
      <label>{t('myAvizosNewDate')}<input type="date" required value={date} onChange={e => setDate(e.target.value)} /></label>
      <label>{t('myAvizosNewTime')}<input type="time" value={time} onChange={e => setTime(e.target.value)} /></label>
      <label style={{ flex: 1, minWidth: 180 }}>{t('notes')}
        <input value={note} maxLength={1000} onChange={e => setNote(e.target.value)} /></label>
      <button className="btn small" disabled={busy || !date}>{busy ? '…' : t('myAvizosSend')}</button>
      {error && <p className="error" style={{ width: '100%' }}>{error}</p>}
    </form>
  )
}
