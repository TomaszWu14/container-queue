import { StarIcon } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { formatDate } from '../dates'
import { LoadError, Skeleton } from '../feedback'
import QuoteRequestModal from './QuoteRequestModal'
import type { Container, Named } from '../types'

// Kolejka „do zlecenia": kontenery wymagające wystawienia zlecenia spedycyjnego.
// Multi-select → reużycie istniejącego QuoteRequestModal (tworzy TransportJob).
export default function ForwardingRequestsPage() {
  const t = useT()
  const navigate = useNavigate()
  const [rows, setRows] = useState<Container[]>([])
  const [forwarders, setForwarders] = useState<Named[]>([])
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [showCreate, setShowCreate] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    setLoading(true); setLoadError('')
    api.get<Container[]>('/api/containers/to-forward')
      .then(setRows)
      .catch(err => setLoadError(errorMessage(err)))
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => load(), [load])
  useEffect(() => {
    api.get<Named[]>('/api/forwarders')
      .then(setForwarders).catch(err => setError(errorMessage(err)))
  }, [])

  const toggleSel = (id: number) => setSelected(prev => {
    const n = new Set(prev)
    if (n.has(id)) n.delete(id); else n.add(id)
    return n
  })

  const toggleFlag = async (c: Container) => {
    try {
      await api.patch(`/api/containers/${c.id}/needs-forwarding`, { value: !c.needs_forwarding })
      load()
    } catch (err) { setError(errorMessage(err)) }
  }

  if (loading && rows.length === 0) return <main className="page"><Skeleton rows={6} /></main>
  if (loadError && rows.length === 0)
    return <main className="page"><LoadError message={loadError} onRetry={load} /></main>

  return (
    <main className="page">
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
        <h2 style={{ margin: 0, fontSize: 19 }}>{t('fwqTitle')}</h2>
        {selected.size > 0 && (
          <button className="btn" onClick={() => setShowCreate(true)}>
            {t('fwqCreate')} ({selected.size})
          </button>
        )}
      </div>
      {error && <p className="error">{error}</p>}
      {rows.length === 0 && <p style={{ color: 'var(--muted)' }}>{t('fwqEmpty')}</p>}

      {rows.length > 0 && (
        <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="grid">
            <thead>
              <tr>
                <th></th>
                <th>{t('containerNo')}</th><th>{t('port')}</th><th>{t('warehouse')}</th>
                <th>{t('eta')}</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(c => (
                <tr key={c.id}>
                  <td><input aria-label={t('fieldSelectRow')} type="checkbox" checked={selected.has(c.id)}
                             onChange={() => toggleSel(c.id)} /></td>
                  <td className="mono">
                    <a className="order-link" onClick={() => navigate(`/kontenery/${c.id}`)}>
                      {c.container_no}
                    </a>
                  </td>
                  <td>{c.port_name}</td>
                  <td>{c.warehouse_name}</td>
                  <td>{formatDate(c.eta)}</td>
                  <td>
                    <button className="btn small secondary"
                            title={c.needs_forwarding ? t('fwqFlagOff') : t('fwqFlagOn')}
                            onClick={() => toggleFlag(c)}>
                      <StarIcon size={14} fill={c.needs_forwarding ? 'currentColor' : 'none'} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <QuoteRequestModal
          containers={rows.filter(c => selected.has(c.id))}
          forwarders={forwarders}
          onDone={() => { setShowCreate(false); setSelected(new Set()); load() }}
          onClose={() => setShowCreate(false)}
        />
      )}
    </main>
  )
}
