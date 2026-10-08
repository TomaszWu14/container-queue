import { FormEvent, useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'

// Ustawienia SMS do kierowców (decyzja 2026-09-28): godzina (czas PL), dni przed dostawą, limit spedytora
type Sms = { reminder_enabled: boolean; reminder_hour: number; reminder_days_before: number[];
  forwarder_daily_limit: number }

export default function SmsSettingsTab() {
  const t = useT()
  const [form, setForm] = useState<Sms | null>(null)
  const [days, setDays] = useState('')
  const [msg, setMsg] = useState('')
  useEffect(() => {
    api.get<Sms>('/api/admin/sms-settings').then(s => { setForm(s); setDays(s.reminder_days_before.join(', ')) })
      .catch(e => setMsg(errorMessage(e)))
  }, [])
  if (!form) return <p className="muted">{msg || '…'}</p>
  const save = async (e: FormEvent) => {
    e.preventDefault()
    try {
      const body = { ...form, reminder_days_before: days.split(',').map(d => Number(d.trim())).filter(d => !Number.isNaN(d)) }
      const saved = await api.put<Sms>('/api/admin/sms-settings', body)
      setForm(saved); setDays(saved.reminder_days_before.join(', ')); setMsg(t('smsSaved'))
    } catch (err) { setMsg(errorMessage(err)) }
  }
  return (
    <form className="panel" onSubmit={save} style={{ display: 'grid', gap: 12, maxWidth: 480 }}>
      <p className="muted" style={{ margin: 0 }}>{t('smsSettingsHint')}</p>
      <label><input type="checkbox" checked={form.reminder_enabled}
        onChange={e => setForm({ ...form, reminder_enabled: e.target.checked })} /> {t('smsReminderEnabled')}</label>
      <label>{t('smsReminderHour')}
        <input type="number" min={0} max={23} value={form.reminder_hour}
          onChange={e => setForm({ ...form, reminder_hour: Number(e.target.value) })} /></label>
      <label>{t('smsReminderDays')}
        <input value={days} onChange={e => setDays(e.target.value)} placeholder="2, 1" /></label>
      <label>{t('smsForwarderLimit')}
        <input type="number" min={0} max={50} value={form.forwarder_daily_limit}
          onChange={e => setForm({ ...form, forwarder_daily_limit: Number(e.target.value) })} /></label>
      <div><button className="btn">{t('save')}</button> <span role="status" className="muted">{msg}</span></div>
    </form>
  )
}
