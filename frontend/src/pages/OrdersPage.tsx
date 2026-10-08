import { PackageSearch } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useUser } from '../App'
import { seesCustoms } from '../routing'
import { api, errorMessage } from '../api'
import { totalOf } from '../listTotal'
import { CustomsBadge, StatusBadge } from '../components'
import { useT } from '../i18n'
import { PageHeader } from '../PageHeader'
import { formatDate } from '../dates'
import type { Container } from '../types'
import { EmptyState, LoadError, Skeleton } from '../feedback'

interface OrderProgress {
  total: number
  delivered: number
  at_port_or_customs: number
  in_transit: number
  delayed: number
  percent: number
  derived_status: string
}

interface Order {
  id: number
  number: string
  company_name: string | null
  supplier_name: string | null
  notes: string
  container_count: number
  progress: OrderProgress
}

interface OrderDetail extends Order {
  containers: Container[]
}

function ProgressBar({ progress }: { progress: OrderProgress }) {
  const t = useT()
  if (progress.total === 0) {
    return <span style={{ color: 'var(--muted)', fontSize: 13 }}>{t('poEmpty')}</span>
  }
  const parts = [
    { count: progress.delivered, color: '#12b76a', label: t('poDelivered') },
    { count: progress.at_port_or_customs, color: '#f79009', label: t('poAtPort') },
    { count: progress.in_transit, color: '#2970ff', label: t('poInTransit') },
  ].filter(p => p.count > 0)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 180 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{
          display: 'flex', flex: 1, height: 10, borderRadius: 5,
          overflow: 'hidden', background: '#eef2f7',
        }}>
          {parts.map(p => (
            <div key={p.label} title={`${p.label}: ${p.count}`}
                 style={{ flex: p.count, background: p.color, height: '100%' }} />
          ))}
        </div>
        <span style={{ fontSize: 13, color: 'var(--muted)', minWidth: 34 }}>
          {progress.percent}%
        </span>
      </div>
      {/* widoczna mini-legenda kolorów (nie tylko title na hover) */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 10px' }}>
        {parts.map(p => (
          <span key={p.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 4,
                                       fontSize: 12, color: 'var(--muted)' }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: p.color }} />
            {p.label} {p.count}
          </span>
        ))}
      </div>
    </div>
  )
}

function DerivedBadge({ status }: { status: string }) {
  const t = useT()
  const classes: Record<string, string> = {
    PUSTE: 'st-ZAPOWIEDZIANY', NOWE: 'st-W_TRANSPORCIE',
    W_TOKU: 'st-W_DOSTAWIE', ZAKONCZONE: 'st-ZREALIZOWANY',
  }
  return <span className={`badge ${classes[status] ?? ''}`}>{t(`po_${status}`)}</span>
}

export function OrderDetailPage() {
  const { id } = useParams()
  const t = useT()
  const showCustoms = seesCustoms(useUser()?.role)
  const navigate = useNavigate()
  const [order, setOrder] = useState<OrderDetail | null>(null)
  const [loadError, setLoadError] = useState('')

  const load = useCallback(() => {
    setLoadError('')
    api.get<OrderDetail>(`/api/orders/${id}`)
      .then(o => { setOrder(o); setLoadError('') })
      .catch(err => setLoadError(errorMessage(err)))
  }, [id])

  useEffect(() => { load() }, [load])

  if (loadError && !order) return (
    <main className="page"><LoadError message={loadError} onRetry={load} /></main>
  )
  if (!order) return <main className="page"><Skeleton rows={5} /></main>

  return (
    <main className="page">
      <div className="panel">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h1 className="m0">{t('order')} {order.number}</h1>
          <DerivedBadge status={order.progress.derived_status} />
        </div>
        <div className="detail-grid">
          <div className="item"><b>{t('company')}</b>{order.company_name || '—'}</div>
          <div className="item"><b>{t('supplier')}</b>{order.supplier_name || '—'}</div>
          <div className="item"><b>{t('poContainers')}</b>{order.container_count}</div>
          <div className="item"><b>{t('poDelivered')}</b>
            {order.progress.delivered} / {order.progress.total}</div>
          {order.notes && <div className="item"><b>{t('notes')}</b>{order.notes}</div>}
        </div>
        <ProgressBar progress={order.progress} />
      </div>

      <div className="panel">
        <h3>{t('poContainers')}</h3>
        <div style={{ overflowX: 'auto' }}>
          <table className="grid">
            <thead>
              <tr>
                <th>{t('containerNo')}</th><th>{t('eta')}</th><th>{t('notifyDate')}</th>
                <th>{t('status')}</th>{showCustoms && <th>{t('customs')}</th>}<th>{t('forwarder')}</th>
              </tr>
            </thead>
            <tbody>
              {order.containers.map(c => (
                <tr key={c.id} className="clickable"
                    onClick={() => navigate(`/kontenery/${c.id}`)}>
                  <td className="mono">
                    {c.container_no}{' '}
                    {c.is_delayed && <span className="badge delayed">{t('delayed')}</span>}
                  </td>
                  <td>{formatDate(c.eta)}</td>
                  <td>{formatDate(c.notify_date)}</td>
                  <td><StatusBadge status={c.status} /></td>
                  {showCustoms && <td><CustomsBadge status={c.customs_status} /></td>}
                  <td>{c.forwarder_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  )
}

export default function OrdersPage() {
  const t = useT()
  const navigate = useNavigate()
  const [orders, setOrders] = useState<Order[]>([])
  const [q, setQ] = useState('')
  const [total, setTotal] = useState<number | null>(null)   // X-Total-Count (limit listy, PERF-003)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadSeq = useRef(0)
  const load = useCallback((query: string) => {
    // straż kolejności: spóźniona odpowiedź wolniejszego zapytania nie nadpisze nowszego
    // (sam debounce/timer nie chroni odpowiedzi już w locie)
    const seq = ++loadSeq.current
    setLoading(true)
    setError('')
    const params = query ? `?q=${encodeURIComponent(query)}` : ''
    api.get<Order[]>(`/api/orders${params}`)
      .then(data => { if (seq === loadSeq.current) { setOrders(data); setTotal(totalOf(data)) } })
      .catch(err => { if (seq === loadSeq.current) { setOrders([]); setError(errorMessage(err)) } })
      .finally(() => { if (seq === loadSeq.current) setLoading(false) })
  }, [])

  useEffect(() => {
    let ignore = false  // spóźniona odpowiedź nie nadpisze wyniku nowszego zapytania
    const timer = setTimeout(() => { if (!ignore) load(q) }, 250)
    return () => { ignore = true; clearTimeout(timer) }
  }, [q, load])

  return (
    <main className="page">
      <PageHeader title={t('orders')} />
      <div className="filters">
        <input type="text" aria-label={t('poSearch')} placeholder={t('poSearch')} value={q}
               onChange={e => setQ(e.target.value)} />
      </div>
      {total !== null && total > orders.length && (
        <p className="kq-truncated" role="status">
          {t('poTruncated').replace('{shown}', String(orders.length)).replace('{total}', String(total))}
        </p>
      )}
      {loading && orders.length === 0 && <Skeleton rows={4} />}
      {!loading && error && orders.length === 0 && <LoadError message={error} onRetry={() => load(q)} />}
      {!loading && !error && orders.length === 0 && <EmptyState icon={PackageSearch} title={t('poNone')} />}
      {orders.length > 0 && (
        <div className="panel" style={{ padding: 0 }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="grid">
              <thead>
                <tr>
                  <th>{t('order')}</th><th>{t('supplier')}</th>
                  <th className="hide-sm">{t('company')}</th>
                  <th>{t('poContainers')}</th><th>{t('poProgress')}</th>
                  <th>{t('status')}</th>
                </tr>
              </thead>
              <tbody>
                {orders.map(order => (
                  <tr key={order.id} className="clickable"
                      onClick={() => navigate(`/zamowienia/${order.id}`)}>
                    <td className="mono"><b>{order.number}</b></td>
                    <td>{order.supplier_name}</td>
                    <td className="hide-sm">{order.company_name}</td>
                    <td>{order.container_count}</td>
                    <td><ProgressBar progress={order.progress} /></td>
                    <td><DerivedBadge status={order.progress.derived_status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </main>
  )
}
