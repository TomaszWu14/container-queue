// #49 — przegląd audytu: kto/co/kiedy zmienił, przekrojowo po encjach (tylko admin).
import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { formatDateTime } from '../../dates'
import { useT } from '../../i18n'

interface AuditRow {
  id: number; entity_type: string; entity_id: number; field: string | null
  old_value: string | null; new_value: string | null; note: string | null
  user_login: string | null; created_at: string | null
}

export default function AuditTab() {
  const t = useT()
  const [entity, setEntity] = useState('')
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<AuditRow[]>([])
  const [error, setError] = useState('')

  const load = () => {
    setError('')
    const p = new URLSearchParams({ limit: '200' })
    if (entity.trim()) p.set('entity_type', entity.trim())
    if (q.trim()) p.set('q', q.trim())
    api.get<AuditRow[]>(`/api/audit?${p}`)
      .then(r => setRows(Array.isArray(r) ? r : []))
      .catch(e => setError(errorMessage(e)))
  }
  useEffect(load, [])   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="panel">
      <h3>{t('auditTitle')}</h3>
      <div className="row" style={{ marginBottom: 12 }}>
        <input value={entity} aria-label={t('auditEntity')} placeholder={t('auditEntity')} onChange={e => setEntity(e.target.value)}
               onKeyDown={e => { if (e.key === 'Enter') load() }} />
        <input value={q} aria-label={t('auditPhrase')} placeholder={t('auditPhrase')} style={{ minWidth: 220 }}
               onChange={e => setQ(e.target.value)}
               onKeyDown={e => { if (e.key === 'Enter') load() }} />
        <button className="btn" onClick={load}>{t('search')}</button>
      </div>
      {error && <p className="error">{error}</p>}
      <div style={{ overflowX: 'auto' }}>
        <table className="grid">
          <thead><tr>
            <th>{t('auditWhen')}</th><th>{t('auditWho')}</th><th>{t('auditEntity')}</th>
            <th>{t('auditField')}</th><th>{t('auditChange')}</th>
          </tr></thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id}>
                <td className="mono">{formatDateTime(r.created_at)}</td>
                <td>{r.user_login ?? '—'}</td>
                <td className="mono">{r.entity_type} #{r.entity_id}</td>
                <td>{r.field ?? '—'}</td>
                <td>{r.old_value ?? '∅'} → {r.new_value ?? '∅'}
                  {r.note && <div className="muted" style={{ fontSize: 11 }}>{r.note}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
