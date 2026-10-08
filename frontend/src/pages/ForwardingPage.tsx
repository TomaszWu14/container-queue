import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUser } from '../App'
import { api, errorMessage } from '../api'
import { Inbox } from 'lucide-react'
import { EmptyState, LoadError, Skeleton, useToast } from '../feedback'
import { OrderBadge } from '../collaboration'
import FreightInvoicesPanel from './FreightInvoicesPanel'
import { Modal, useDicts } from '../components'
import { useT } from '../i18n'
import type { Container, TransportOrder, TransportOrderStatus } from '../types'
import { formatDate, formatDateTime } from '../dates'
import { useTransportOrderActions } from '../transportOrders'
import { PageHeader } from '../PageHeader'

interface ForwardingKpi {
  total: number
  by_status: Record<string, number>
  avg_realization_days: number | null
  rejection_rate: number
  top_forwarders: { name: string; count: number }[]
}

// Zakładki pogrupowane: najpierw statusy aktywne (wymagają działania), potem zakończone.
const ACTIVE_STATUSES: TransportOrderStatus[] = ['WYSTAWIONE', 'ZAAKCEPTOWANE', 'W_REALIZACJI']
const DONE_STATUSES: TransportOrderStatus[] = ['WYKONANE', 'POTWIERDZONE', 'ODRZUCONE']

function NewOrderModal({ onSaved, onClose }: { onSaved: () => void; onClose: () => void }) {
  const t = useT()
  const dicts = useDicts()
  const [containers, setContainers] = useState<Container[]>([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({
    container_id: '', forwarder_id: '', pickup_location: '', delivery_location: '',
    pickup_date: '', delivery_date: '', instructions: '',
  })

  useEffect(() => {
    api.get<Container[]>('/api/containers?completed=false&limit=2000')
      .then(setContainers).catch(() => {})
  }, [])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return containers
    return containers.filter(c =>
      c.container_no.toLowerCase().includes(needle)
      || (c.order_number ?? '').toLowerCase().includes(needle)
      || (c.supplier_name ?? '').toLowerCase().includes(needle))
  }, [containers, query])

  const pickContainer = (id: string) => {
    const container = containers.find(c => c.id === Number(id))
    setForm(f => ({
      ...f,
      container_id: id,
      forwarder_id: container?.forwarder_id ? String(container.forwarder_id) : f.forwarder_id,
      pickup_location: f.pickup_location || container?.port_name || '',
      delivery_location: f.delivery_location || container?.warehouse_name || '',
    }))
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setError('')
    setBusy(true)
    try {
      await api.post('/api/transport-orders', {
        container_id: Number(form.container_id),
        forwarder_id: form.forwarder_id ? Number(form.forwarder_id) : null,
        pickup_location: form.pickup_location,
        delivery_location: form.delivery_location,
        pickup_date: form.pickup_date || null,
        delivery_date: form.delivery_date || null,
        instructions: form.instructions,
      })
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={t('newOrder')} onClose={onClose} busy={busy}>
        <form onSubmit={submit} className="form-grid">
          <label className="wide">{t('search')}
            <input value={query} onChange={e => setQuery(e.target.value)}
                   placeholder={t('containerNo')} />
          </label>
          <label className="wide">{t('containerNo')}
            <select required value={form.container_id} onChange={e => pickContainer(e.target.value)}>
              <option value="">—</option>
              {filtered.map(c => (
                <option key={c.id} value={c.id}>
                  {c.container_no} · {c.supplier_name ?? ''} {c.order_number ? `· PO ${c.order_number}` : ''}
                </option>
              ))}
            </select>
          </label>
          <label>{t('forwarder')}
            <select value={form.forwarder_id}
                    onChange={e => setForm(f => ({ ...f, forwarder_id: e.target.value }))}>
              <option value="">—</option>
              {dicts.forwarders.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </label>
          <label>{t('pickupDate')}
            <input type="date" value={form.pickup_date}
                   onChange={e => setForm(f => ({ ...f, pickup_date: e.target.value }))} />
          </label>
          <label>{t('pickup')}
            <input value={form.pickup_location}
                   onChange={e => setForm(f => ({ ...f, pickup_location: e.target.value }))} />
          </label>
          <label>{t('delivery')}
            <input value={form.delivery_location}
                   onChange={e => setForm(f => ({ ...f, delivery_location: e.target.value }))} />
          </label>
          <label>{t('deliveryDate')}
            <input type="date" value={form.delivery_date}
                   onChange={e => setForm(f => ({ ...f, delivery_date: e.target.value }))} />
          </label>
          <label className="wide">{t('instructions')}
            <textarea rows={2} value={form.instructions}
                      onChange={e => setForm(f => ({ ...f, instructions: e.target.value }))} />
          </label>
        </form>
        {error && <p className="error">{error}</p>}

        <div className="actions">
          <button className="btn secondary" disabled={busy} onClick={onClose}>{t('cancel')}</button>
          <button className="btn" onClick={submit} disabled={!form.container_id || busy}>{t('save')}</button>
        </div>
    </Modal>
  )
}

export default function ForwardingPage() {
  const t = useT()
  const user = useUser()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [orders, setOrders] = useState<TransportOrder[]>([])
  const [tab, setTab] = useState<'' | 'PLAN' | 'BL' | TransportOrderStatus>('')
  const [pending, setPending] = useState<Container[]>([])
  // data wpisywana przez spedycję zanim potwierdzi — pusta = akceptujemy propozycję
  const [planDates, setPlanDates] = useState<Record<number, string>>({})
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [showNew, setShowNew] = useState(false)

  const isForwarder = user?.role === 'forwarder'
  const canCreate = user?.role === 'admin' || user?.role === 'logistics'

  const load = useCallback(() => {
    setLoading(true)
    setLoadError('')  // nie zostawiaj starego błędu po udanym odświeżeniu
    api.get<TransportOrder[]>('/api/transport-orders')
      .then(setOrders)
      .catch(err => setLoadError(errorMessage(err)))
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => load(), [load])
  // CODE-008: przejścia statusów wspólne z kartą kontenera (transportOrders.tsx)
  const { error, setError, actions, rejectRow } = useTransportOrderActions({
    role: user?.role, onDone: () => { load(); showToast(t('toastOrderStatusChanged')) } })

  const loadPending = useCallback(() => {
    setLoadError('')
    api.get<Container[]>('/api/containers/plan/pending')
      .then(setPending)
      .catch(err => setLoadError(errorMessage(err)))
  }, [])
  useEffect(() => loadPending(), [loadPending])

  const [acting, setActing] = useState(false)
  const [kpi, setKpi] = useState<ForwardingKpi | null>(null)
  useEffect(() => {
    api.get<ForwardingKpi>('/api/transport-orders/kpi').then(setKpi).catch(() => {})
  }, [])
  const confirmPlan = async (id: number, day: string) => {
    if (acting) return
    setError('')
    setActing(true)
    try {
      await api.post(`/api/containers/${id}/plan/confirm`, { delivery_date: day })
      loadPending()
    } catch (err) { setError(errorMessage(err)) } finally { setActing(false) }
  }

  const counts = useMemo(() => {
    const map: Partial<Record<TransportOrderStatus, number>> = {}
    for (const order of orders) map[order.status] = (map[order.status] ?? 0) + 1
    return map
  }, [orders])

  // pusty stan zależny od roli (C11): „Nowe zlecenie” ma tylko admin/logistyka
  const emptyOrders = (
    <EmptyState icon={Inbox} title={t('noOrders')}
                hint={canCreate ? t('noOrdersHint') : isForwarder ? t('noOrdersHintForwarder') : undefined}>
      {canCreate && <button className="btn small" onClick={() => setShowNew(true)}>{t('newOrder')}</button>}
    </EmptyState>
  )

  // liczniki zakładek: przy błędzie wczytania bez „(0)” — to nie są prawdziwe dane (C4)
  const n = (x: number) => loadError ? '' : ` (${x})`

  const visible = tab === 'PLAN' ? []
    : tab ? orders.filter(o => o.status === tab) : orders

  return (
    <main className="page">
      <PageHeader title={t('forwarding')} actions={canCreate && (
        <button className="btn" onClick={() => setShowNew(true)}>{t('newOrder')}</button>
      )} />

      {kpi && kpi.total > 0 && (
        <div className="panel" style={{ display: 'flex', flexWrap: 'wrap', gap: 20, marginBottom: 14 }}>
          <span>{t('fwdKpiTotal')}: <b>{kpi.total}</b></span>
          <span>{t('fwdKpiAvgDays')}: <b>{kpi.avg_realization_days ?? '—'}</b></span>
          <span>{t('fwdKpiRejection')}: <b>{kpi.rejection_rate}%</b></span>
          {kpi.top_forwarders[0] && (
            <span>{t('fwdKpiTop')}: <b>{kpi.top_forwarders[0].name}</b> ({kpi.top_forwarders[0].count})</span>
          )}
        </div>
      )}

      <div className="tabs">
        <button className={tab === '' ? 'active' : ''} onClick={() => setTab('')}>
          {t('allOrders')}{n(orders.length)}
        </button>
        <button className={tab === 'PLAN' ? 'active' : ''} onClick={() => setTab('PLAN')}>
          {t('planPending')}{n(pending.length)}
        </button>
        {ACTIVE_STATUSES.map(s => (
          <button key={s} className={tab === s ? 'active' : ''} onClick={() => setTab(s)}>
            {t(`to_${s}`)}{n(counts[s] ?? 0)}
          </button>
        ))}
        <span className="tabs-sep" aria-hidden />
        {DONE_STATUSES.map(s => (
          <button key={s} className={tab === s ? 'active' : ''} onClick={() => setTab(s)}>
            {t(`to_${s}`)}{n(counts[s] ?? 0)}
          </button>
        ))}
        <span className="tabs-sep" aria-hidden />
        <button className={tab === 'BL' ? 'active' : ''} onClick={() => setTab('BL')}>
          {t('blInvoices')}
        </button>
      </div>

      {tab === 'BL' && <FreightInvoicesPanel />}

      {error && tab !== 'BL' && <p className="error">{error}</p>}
      {loadError && tab !== 'BL' && <LoadError message={loadError} onRetry={() => { load(); loadPending() }} />}
      {tab === 'PLAN' && !loadError && (
        pending.length === 0
          ? emptyOrders
          : <div className="panel p0 table-scroll">
              <table className="grid">
                <thead>
                  <tr>
                    <th>{t('containerNo')}</th><th>{t('vessel')}</th><th>{t('warehouse')}</th>
                    <th>{t('planYourDate')}</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {pending.map(c => {
                    const day = planDates[c.id] ?? c.notify_date ?? ''
                    return (
                      <tr key={c.id}>
                        <td className="mono">
                          <a className="order-link" onClick={() => navigate(`/kontenery/${c.id}`)}>
                            {c.container_no}
                          </a>
                        </td>
                        <td>{c.vessel}</td>
                        <td>{c.warehouse_name}</td>
                        <td>
                          <input type="date" value={day} aria-label={t('planCounterDate')}
                                 onChange={e => setPlanDates(prev => ({ ...prev, [c.id]: e.target.value }))} />
                        </td>
                        <td>
                          <button className="btn small" disabled={!day || acting}
                                  onClick={() => confirmPlan(c.id, day)}>
                            {t('planConfirmDate')}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
      )}
      {tab !== 'PLAN' && tab !== 'BL' && loading && orders.length === 0 && <Skeleton rows={6} />}
      {tab !== 'PLAN' && tab !== 'BL' && !loading && !loadError && visible.length === 0 && (
        emptyOrders
      )}

      {visible.length > 0 && (
        <div className="panel p0 table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th>{t('containerNo')}</th>
                {!isForwarder && <th>{t('forwarder')}</th>}
                <th>{t('status')}</th>
                <th>{t('route')}</th>
                <th>{t('pickupDate')}</th>
                <th>{t('deliveryDate')}</th>
                <th className="hide-sm">{t('createdBy')}</th>
                <th className="hide-sm">{t('when')}</th>
                <th>{t('notes')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visible.map(order => (
                <tr key={order.id}>
                  <td className="mono">
                    <a className="order-link"
                       onClick={() => navigate(`/kontenery/${order.container_id}`)}>
                      {order.container_no ?? `#${order.container_id}`}
                    </a>
                  </td>
                  {!isForwarder && <td>{order.forwarder_name}</td>}
                  <td><OrderBadge status={order.status} /></td>
                  <td>
                    {order.pickup_location || '—'}
                    <span style={{ color: 'var(--muted)' }}> → </span>
                    {order.delivery_location || '—'}
                  </td>
                  <td>{formatDate(order.pickup_date)}</td>
                  <td>{formatDate(order.delivery_date)}</td>
                  <td className="hide-sm">{order.created_by_login}</td>
                  <td className="hide-sm">{formatDateTime(order.created_at)}</td>
                  <td className="notes-cell">
                    {order.status === 'ODRZUCONE' && order.rejection_reason
                      ? `${t('rejectionReason')}: ${order.rejection_reason}`
                      : order.instructions}
                  </td>
                  <td className="row" style={{ flexWrap: 'nowrap' }}>{actions(order)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rejectRow}
        </div>
      )}

      {showNew && <NewOrderModal onSaved={load} onClose={() => setShowNew(false)} />}
    </main>
  )
}
