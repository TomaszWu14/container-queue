import { FormEvent, useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import { formatDateTime } from '../../dates'

type Health = {
  status: string, version: string, uptime_s: number,
  last_ais_seen: string | null, last_tracking_sync: string | null,
}

function SystemPanel() {
  const t = useT()
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => { api.get<Health>('/api/health').then(setHealth).catch(() => {}) }, [])

  const fmt = (iso: string | null) => iso ? formatDateTime(iso) : t('systemNever')
  const uptime = (s: number) => `${Math.floor(s / 3600)}h ${Math.floor(s % 3600 / 60)}m`

  return (
    <div className="panel">
      <h3>{t('systemPanel')}</h3>
      {!health ? <p>{t('systemUnavailable')}</p> : (
        <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '4px 12px', margin: 0 }}>
          <dt style={{ color: 'var(--muted)' }}>{t('systemVersion')}</dt><dd>{health.version}</dd>
          <dt style={{ color: 'var(--muted)' }}>{t('systemUptime')}</dt><dd>{uptime(health.uptime_s)}</dd>
          <dt style={{ color: 'var(--muted)' }}>{t('systemLastAis')}</dt><dd>{fmt(health.last_ais_seen)}</dd>
          <dt style={{ color: 'var(--muted)' }}>{t('systemLastTracking')}</dt><dd>{fmt(health.last_tracking_sync)}</dd>
        </dl>
      )}
    </div>
  )
}

export default function SettingsTab() {
  const t = useT()
  const [form, setForm] = useState({ reminder_days: '15,30', insurer_email: '', complaint_prefix: 'REK', docs_reminder_days: '7', forecast_alert_days: '7', warehouse_eta_buffer_days: '3' })
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => { api.get<typeof form>('/api/settings').then(setForm).catch(() => {}) }, [])

  const save = async (event: FormEvent) => {
    event.preventDefault()
    setError(''); setSaved(false)
    // reminder_days trafia na backend jako CSV liczb — pusty/śmieciowy string psuje przypomnienia
    if (!/^\s*\d+(\s*,\s*\d+)*\s*$/.test(form.reminder_days)) {
      setError(t('reminderDaysInvalid')); return
    }
    try {
      const out = await api.put<typeof form>('/api/settings', form)
      setForm(out); setSaved(true)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div className="panel">
      <h3>{t('settingsTab')}</h3>
      <form className="form-grid" onSubmit={save} style={{ maxWidth: 560 }}>
        <label>{t('reminderDays')}
          <input value={form.reminder_days}
                 onChange={e => setForm(f => ({ ...f, reminder_days: e.target.value }))} />
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{t('reminderDaysHint')}</span>
        </label>
        <label>{t('insurerEmail')}
          <input type="email" value={form.insurer_email}
                 onChange={e => setForm(f => ({ ...f, insurer_email: e.target.value }))} />
        </label>
        <label>{t('docsReminderDays')}
          <input type="number" min={1} value={form.docs_reminder_days}
                 onChange={e => setForm(f => ({ ...f, docs_reminder_days: e.target.value }))} />
        </label>
        <label>{t('forecastAlertDays')}
          <input type="number" min={1} value={form.forecast_alert_days}
                 onChange={e => setForm(f => ({ ...f, forecast_alert_days: e.target.value }))} />
        </label>
        <label>{t('warehouseEtaBufferDays')}
          <input type="number" min={0} value={form.warehouse_eta_buffer_days}
                 onChange={e => setForm(f => ({ ...f, warehouse_eta_buffer_days: e.target.value }))} />
        </label>
        <label>{t('complaintPrefix')}
          <input value={form.complaint_prefix}
                 onChange={e => setForm(f => ({ ...f, complaint_prefix: e.target.value }))} />
        </label>
        <div className="wide" style={{ textAlign: 'right' }}>
          {saved && <span style={{ color: '#047857', marginRight: 10 }}>✓ {t('saved')}</span>}
          <button className="btn">{t('save')}</button>
        </div>
      </form>
      {error && <p className="error">{error}</p>}
      <SystemPanel />
    </div>
  )
}
