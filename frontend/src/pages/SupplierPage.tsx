import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api'
import { LoadError, Skeleton } from '../feedback'
import { Kpi, StatusBadge } from '../components'
import { useT } from '../i18n'
import type { Supplier, SupplierStats } from '../types'
import { formatDate } from '../dates'
import { useUser } from '../App'
import DocProfileCard, { PROFILE_READERS } from './supplierProfile/DocProfileCard'

export default function SupplierPage() {
  const { id } = useParams()
  const t = useT()
  const navigate = useNavigate()
  const user = useUser()
  const [supplier, setSupplier] = useState<Supplier | null>(null)
  const [stats, setStats] = useState<SupplierStats | null>(null)
  const [loadError, setLoadError] = useState('')

  const loadSeq = useRef(0)
  const load = useCallback(() => {
    const seq = ++loadSeq.current
    setSupplier(null)
    setStats(null)
    setLoadError('')
    api.get<Supplier[]>(`/api/suppliers?include_inactive=true`)
      .then(list => {
        if (seq !== loadSeq.current) return
        const found = list.find(s => String(s.id) === id)
        if (!found) { setLoadError(t('err404Body')); return }
        setSupplier(found)
      })
      .catch(err => { if (seq === loadSeq.current) setLoadError(errorMessage(err)) })
    api.get<SupplierStats>(`/api/suppliers/${id}/stats`)
      .then(s => { if (seq === loadSeq.current) setStats(s) })
      .catch(() => {})
  }, [id, t])

  useEffect(() => load(), [load])

  if (loadError && !supplier) return (
    <main className="page"><LoadError message={loadError} onRetry={load} /></main>
  )
  if (!supplier) return <main className="page"><Skeleton rows={6} /></main>

  return (
    <main className="page">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>{supplier.name}</h2>
      </div>
      <section className="panel">
        <div className="detail-grid">
          <div className="item"><b>{t('supplierAddress')}</b>{supplier.address || '—'}</div>
          <div className="item"><b>{t('supplierNote')}</b>{supplier.note || '—'}</div>
        </div>
      </section>

      <div className="dash-kpis">
        <Kpi label={t('supplierActiveContainers')} value={stats ? stats.active_containers : '—'} />
        <Kpi label={t('supplierOnTimePct')}
          value={stats && stats.on_time_pct !== null ? `${stats.on_time_pct}%` : t('supplierNoStats')} />
        <Kpi label={t('supplierAvgTransit')}
          value={stats && stats.avg_transit_days !== null
            ? `${stats.avg_transit_days} ${t('supplierDays')}` : t('supplierNoStats')} />
      </div>

      {user && PROFILE_READERS.includes(user.role) && (
        <DocProfileCard supplierId={supplier.id} supplierName={supplier.name} />
      )}

      <section className="panel">
        <h3>{t('supplierRecentContainers')}</h3>
        <table className="grid">
          <thead>
            <tr>
              <th>{t('containerNo')}</th>
              <th>{t('status')}</th>
              <th>{t('eta')}</th>
              <th>ATD</th>
            </tr>
          </thead>
          <tbody>
            {(stats?.recent_containers ?? []).map(c => (
              <tr key={c.id} className="link-like"
                  onClick={() => navigate(`/kontenery/${c.id}`)}>
                <td className="mono">{c.container_no}</td>
                <td><StatusBadge status={c.status as never} /></td>
                <td className="nowrap mono">{c.eta ? formatDate(c.eta) : '—'}</td>
                <td className="nowrap mono">{c.atd ? formatDate(c.atd) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  )
}
