import { FormEvent, useEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import { formatDateTime } from '../../dates'
import { DictTable } from './shared'
import { useBusy } from '../../useBusy'

interface AuthLogEntry {
  id: number
  field: string
  login: string
  note: string
  created_at: string
}

interface BlockedIp {
  id: number
  ip: string
  note: string
}

const IP_RE = /\b\d{1,3}(?:\.\d{1,3}){3}\b/

export default function AuthLogTab() {
  const t = useT()
  const [entries, setEntries] = useState<AuthLogEntry[]>([])
  const [blocked, setBlocked] = useState<BlockedIp[]>([])
  const [error, setError] = useState('')
  const [filters, setFilters] = useState({ q: '', ip: '', date_from: '', date_to: '' })
  const [newIp, setNewIp] = useState({ ip: '', note: '' })

  // ładowanie tylko na starcie i na „Filtruj" (nie na każdy znak); numer żądania
  // odrzuca spóźnioną odpowiedź starszego filtra
  const seq = useRef(0)
  const load = () => {
    const my = ++seq.current
    const params = new URLSearchParams()
    for (const [k, v] of Object.entries(filters)) if (v) params.set(k, v)
    api.get<AuthLogEntry[]>(`/api/admin/auth-log?${params}`)
      .then(rows => { if (my === seq.current) { setEntries(rows); setError('') } })
      .catch(err => { if (my === seq.current) setError(errorMessage(err)) })
  }

  const loadBlocked = () => api.get<BlockedIp[]>('/api/admin/blocked-ips')
    .then(setBlocked).catch(err => setError(errorMessage(err)))

  useEffect(() => { load(); loadBlocked() }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  const applyFilters = (e: FormEvent) => { e.preventDefault(); load() }

  // dwuklik „Zablokuj”/„Dodaj”/„Odblokuj” = jedno żądanie (bez 409 duplikatu / 404)
  const { busy, run } = useBusy()
  const blockIp = (ip: string, note: string) => run(async () => {
    setError('')
    try {
      await api.post('/api/admin/blocked-ips', { ip, note })
      loadBlocked()
    } catch (err) { setError(errorMessage(err)) }
  })

  const addBlocked = async (e: FormEvent) => {
    e.preventDefault()
    if (!newIp.ip.trim()) return
    await blockIp(newIp.ip.trim(), newIp.note.trim())
    setNewIp({ ip: '', note: '' })
  }

  const unblock = (b: BlockedIp) => run(async () => {
    setError('')
    try { await api.del(`/api/admin/blocked-ips/${b.id}`); loadBlocked() }
    catch (err) { setError(errorMessage(err)) }
  })

  return (
    <div className="panel">
      <h3>{t('authLogTitle')}</h3>
      {error && <p className="error">{error}</p>}
      <form className="row" onSubmit={applyFilters} style={{ marginBottom: 12 }}>
        <input aria-label={t('authLogAccount')} placeholder={t('authLogAccount')} value={filters.q}
               onChange={e => setFilters(f => ({ ...f, q: e.target.value }))} />
        <input aria-label="IP" placeholder="IP" value={filters.ip}
               onChange={e => setFilters(f => ({ ...f, ip: e.target.value }))} />
        <input type="date" value={filters.date_from} title={t('dateFrom')}
               onChange={e => setFilters(f => ({ ...f, date_from: e.target.value }))} />
        <input type="date" value={filters.date_to} title={t('dateTo')}
               onChange={e => setFilters(f => ({ ...f, date_to: e.target.value }))} />
        <button className="btn secondary">{t('authLogFilter')}</button>
      </form>
      <DictTable cols={[{ label: t('authLogWhen'), width: '160px' },
                        { label: t('authLogEvent'), width: '140px' },
                        t('loginField'), t('mdNote'), { width: '130px' }]}>
        {entries.map(e => {
          const ip = e.note.match(IP_RE)?.[0]
          return (
            <tr key={e.id}>
              <td>{formatDateTime(e.created_at)}</td>
              <td>{e.field}</td>
              <td>{e.login}</td>
              <td>{e.note}</td>
              <td>
                {ip && (
                  <button className="btn small secondary" disabled={busy}
                          onClick={() => blockIp(ip, `${e.field}: ${e.login}`)}>
                    {t('authLogBlockIp')}
                  </button>
                )}
              </td>
            </tr>
          )
        })}
      </DictTable>

      <div className="panel" style={{ marginTop: 16 }}>
        <h3>{t('blockedIpsTitle')}</h3>
        <form className="row" onSubmit={addBlocked} style={{ marginBottom: 12 }}>
          <input aria-label="IP" placeholder="IP" value={newIp.ip} required
                 onChange={e => setNewIp(f => ({ ...f, ip: e.target.value }))} />
          <input aria-label={t('mdNote')} placeholder={t('mdNote')} value={newIp.note}
                 onChange={e => setNewIp(f => ({ ...f, note: e.target.value }))} />
          <button className="btn" disabled={busy}>{t('add')}</button>
        </form>
        <DictTable cols={['IP', t('mdNote'), { width: '110px' }]}>
          {blocked.map(b => (
            <tr key={b.id}>
              <td>{b.ip}</td>
              <td>{b.note}</td>
              <td>
                <button className="btn small danger" disabled={busy} onClick={() => unblock(b)}>
                  {t('deleteBtn')}
                </button>
              </td>
            </tr>
          ))}
        </DictTable>
      </div>
    </div>
  )
}
