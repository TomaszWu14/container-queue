import { Inbox, ShoppingCart } from 'lucide-react'
import { Fragment, useCallback, useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { useConfirm } from '../ConfirmDialog'
import { formatDate, formatNum } from '../dates'
import { EmptyState, LoadError, Skeleton, useToast } from '../feedback'
import { PageHeader } from '../PageHeader'

interface CartOrder {
  id: number
  order_no: string
  supplier: string | null
  cbm: number | null
  crd: string | null
  crd_target: string | null
  deviation_days: number | null
  cart_status: 'w_koszyku' | 'zwolnione' | 'przypisane' | 'zablokowane'
  container_id: number | null
}

interface OpenContainer {
  id: number
  container_no: string
  consolidation_status: string
  capacity_cbm: number
  fill_cbm: number
  crd: string | null
  order_count: number
}

interface Proposal {
  supplier: string
  orders: number[]
  total_cbm: number
  order_names?: string[]
  port_of_departure?: string | null
  port_of_discharge?: string | null
  fill_pct?: number | null
}

interface ContainerOrders {
  orders: CartOrder[]
  fill_cbm: number
  crd: string | null
  capacity_cbm: number
  consolidation_status: string
}

function CartBadge({ status }: { status: CartOrder['cart_status'] }) {
  const t = useT()
  const classes: Record<string, string> = {
    w_koszyku: 'st-ZAPOWIEDZIANY', zwolnione: 'st-W_TRANSPORCIE',
    przypisane: 'st-ZREALIZOWANY', zablokowane: 'delayed',
  }
  return <span className={`badge ${classes[status] ?? ''}`}>{t(`cart_${status}`)}</span>
}

function FillBar({ fill, capacity }: { fill: number; capacity: number }) {
  const pct = capacity > 0 ? (fill / capacity) * 100 : 0
  const over = pct >= 100
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 160 }}>
      <div style={{ flex: 1, height: 10, borderRadius: 5, background: 'var(--soft)', overflow: 'hidden' }}>
        <div style={{
          width: `${Math.min(pct, 100)}%`, height: '100%',
          background: over ? 'var(--danger)' : 'var(--accent)',
        }} />
      </div>
      <span style={{ fontSize: 13, color: over ? 'var(--danger)' : 'var(--muted)', minWidth: 80 }}>
        {formatNum(fill, 1)} / {formatNum(capacity, 1)} m³
      </span>
    </div>
  )
}

export default function KoszykPage() {
  const t = useT()
  const { confirm } = useConfirm()
  const { showToast } = useToast()
  const [cart, setCart] = useState<CartOrder[] | null>(null)
  const [containers, setContainers] = useState<OpenContainer[] | null>(null)
  const [proposals, setProposals] = useState<Proposal[] | null>(null)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [expandedOrders, setExpandedOrders] = useState<ContainerOrders | null>(null)
  const [assignTarget, setAssignTarget] = useState<Record<number, string>>({})
  const [proposalTarget, setProposalTarget] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState<number | null>(null)
  const [proposalBusy, setProposalBusy] = useState<number | null>(null)
  const [crdEdits, setCrdEdits] = useState<Record<number, { crd: string; crd_target: string }>>({})

  const crdFor = (o: CartOrder) => crdEdits[o.id] ?? { crd: o.crd ?? '', crd_target: o.crd_target ?? '' }
  const setCrdField = (o: CartOrder, field: 'crd' | 'crd_target', value: string) =>
    setCrdEdits(m => ({ ...m, [o.id]: { ...crdFor(o), [field]: value } }))

  const saveCrd = (o: CartOrder) => {
    const { crd, crd_target } = crdFor(o)
    runAction(o.id, () => api.patch(`/api/purchase-orders/${o.id}/crd`, { crd: crd || null, crd_target: crd_target || null }))
  }

  const load = useCallback(() => {
    setError('')
    Promise.all([
      api.get<CartOrder[]>('/api/purchase-orders?cart_status=w_koszyku'),
      api.get<CartOrder[]>('/api/purchase-orders?cart_status=zwolnione'),
      api.get<OpenContainer[]>('/api/consolidation/containers?status=otwarty'),
      api.get<Proposal[]>('/api/consolidation/proposals'),
    ]).then(([waiting, released, cont, props]) => {
      setCart([...waiting, ...released])
      setContainers(cont)
      setProposals(props)
    }).catch(err => setError(errorMessage(err)))
  }, [])

  useEffect(() => { load() }, [load])

  const loadExpanded = useCallback((cid: number) => {
    api.get<ContainerOrders>(`/api/containers/${cid}/orders`)
      .then(setExpandedOrders)
      .catch(err => showToast(errorMessage(err), 'error'))
  }, [showToast])

  const toggleExpand = (cid: number) => {
    if (expanded === cid) { setExpanded(null); setExpandedOrders(null); return }
    setExpanded(cid)
    loadExpanded(cid)
  }

  const runAction = async (id: number, action: () => Promise<unknown>) => {
    setBusy(id)
    try {
      await action()
      load()
      if (expanded) loadExpanded(expanded)
    } catch (err) {
      showToast(errorMessage(err), 'error')
    } finally {
      setBusy(null)
    }
  }

  const applyProposal = async (idx: number, p: Proposal) => {
    const cid = proposalTarget[idx]
    if (!cid) return
    setProposalBusy(idx)
    try {
      for (const poId of p.orders) {
        await api.put(`/api/containers/${cid}/orders/${poId}`, {})
      }
      load()
    } catch (err) {
      showToast(errorMessage(err), 'error')
    } finally {
      setProposalBusy(null)
    }
  }

  if (error && !cart) return <main className="page"><LoadError message={error} onRetry={load} /></main>
  if (!cart || !containers || !proposals) return <main className="page"><Skeleton rows={5} /></main>

  // C31: puste konsolidacje (0 m³, 0 zamówień) zwinięte w osobnej sekcji — nic nie usuwamy
  const isEmpty = (c: OpenContainer) => c.fill_cbm <= 0 && c.order_count === 0
  const filled = containers.filter(c => !isEmpty(c))
  const empty = containers.filter(isEmpty)
  const containerRow = (c: OpenContainer) => (
    <Fragment key={c.id}>
      <tr className="clickable" onClick={() => toggleExpand(c.id)}>
        <td className="mono">{c.container_no}</td>
        <td><FillBar fill={c.fill_cbm} capacity={c.capacity_cbm} /></td>
        <td>{c.crd ? formatDate(c.crd) : '—'}</td>
        <td>{c.order_count}</td>
        <td>
          {c.fill_cbm > 0 && (
            <button className="btn small secondary" disabled={busy === c.id}
                    onClick={e => { e.stopPropagation()
                      runAction(c.id, () => api.post(`/api/containers/${c.id}/close-consolidation`, {})) }}>
              {t('closeConsolidation')}
            </button>
          )}
        </td>
      </tr>
      {expanded === c.id && (
        <tr>
          <td colSpan={5}>
            {!expandedOrders ? <Skeleton rows={2} /> : (
              expandedOrders.orders.length === 0 ? <p>{t('emptyCart')}</p> : (
                <table className="grid">
                  <thead>
                    <tr><th>{t('order')}</th><th>{t('supplier')}</th><th>{t('poCbm')}</th><th><span className="sr-only">{t('actions')}</span></th></tr>
                  </thead>
                  <tbody>
                    {expandedOrders.orders.map(o => (
                      <tr key={o.id}>
                        <td className="mono">{o.order_no}</td>
                        <td>{o.supplier}</td>
                        <td>{o.cbm ?? ''}</td>
                        <td>
                          <button className="btn small secondary" disabled={busy === o.id}
                                  onClick={async () => (await confirm(t('cartUnassignConfirm').replace('{order}', o.order_no)))
                                    && runAction(o.id, () => api.del(`/api/containers/${c.id}/orders/${o.id}`))}>
                            {t('unassign')}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            )}
          </td>
        </tr>
      )}
    </Fragment>
  )

  return (
    <main className="page">
      <PageHeader title={t('koszykTitle')} />

      <div className="panel">
        <h2 className="as-h3">{t('proposalsSection')}</h2>
        {proposals.length === 0 ? <EmptyState bare icon={Inbox} title={t('noProposals')} /> : (
          <div style={{ overflowX: 'auto' }}>
            <table className="grid">
              <thead>
                <tr><th>{t('supplier')}</th><th>{t('proposalRoute')}</th><th>{t('proposalOrders')}</th><th>{t('poCbm')}</th><th><span className="sr-only">{t('actions')}</span></th></tr>
              </thead>
              <tbody>
                {proposals.map((p, idx) => {
                  const route = [p.port_of_departure, p.port_of_discharge].filter(Boolean).join(' → ')
                  return (
                  <tr key={idx}>
                    <td>{p.supplier}</td>
                    <td className="mono" style={{ fontSize: 13 }}>{route || '—'}</td>
                    <td>{p.order_names ? p.order_names.join(', ') : `${p.orders.length} ${t('proposalOrders')}`}</td>
                    <td><FillBar fill={p.total_cbm} capacity={70} /></td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <select aria-label={t('assign')} value={proposalTarget[idx] ?? ''} disabled={proposalBusy === idx}
                                onChange={e => setProposalTarget(m => ({ ...m, [idx]: e.target.value }))}>
                          <option value="">{t('assign')}…</option>
                          {containers.map(c => (
                            <option key={c.id} value={c.id}>{c.container_no}</option>
                          ))}
                        </select>
                        <button className="btn small" disabled={proposalBusy === idx || !proposalTarget[idx]}
                                onClick={() => applyProposal(idx, p)}>
                          {t('applyProposal')}
                        </button>
                      </div>
                    </td>
                  </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel">
        <h2 className="as-h3">{t('koszykSection')}</h2>
        {cart.length === 0 ? <EmptyState bare icon={ShoppingCart} title={t('emptyCart')} /> : (
          <div style={{ overflowX: 'auto' }}>
            <table className="grid">
              <thead>
                <tr>
                  <th>{t('order')}</th><th>{t('supplier')}</th><th>{t('poCbm')}</th>
                  <th>{t('crdLabel')}</th><th>{t('crdTargetLabel')}</th>
                  <th>{t('status')}</th><th><span className="sr-only">{t('actions')}</span></th>
                </tr>
              </thead>
              <tbody>
                {cart.map(o => {
                  const edit = crdFor(o)
                  const dev = o.deviation_days
                  return (
                  <tr key={o.id}>
                    <td className="mono">{o.order_no}</td>
                    <td>{o.supplier}</td>
                    <td>{o.cbm ?? ''}</td>
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <input aria-label={t('crdLabel')} type="date" value={edit.crd} disabled={busy === o.id}
                               onChange={e => setCrdField(o, 'crd', e.target.value)} />
                        {dev != null && (
                          <span className="badge"
                                style={dev >= 10 ? { color: 'var(--danger)', borderColor: 'var(--danger)' } : undefined}>
                            {dev} {t('deviationDaysUnit')}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <input aria-label={t('crdTargetLabel')} type="date" value={edit.crd_target} disabled={busy === o.id}
                               onChange={e => setCrdField(o, 'crd_target', e.target.value)} />
                        <button className="btn small" disabled={busy === o.id}
                                onClick={() => saveCrd(o)}>
                          {t('saveCrd')}
                        </button>
                      </div>
                    </td>
                    <td><CartBadge status={o.cart_status} /></td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {o.cart_status === 'w_koszyku' && (
                          <button className="btn small" disabled={busy === o.id}
                                  onClick={() => runAction(o.id, () => api.post(`/api/purchase-orders/${o.id}/release`, {}))}>
                            {t('release')}
                          </button>
                        )}
                        {o.cart_status === 'zwolnione' && (
                          <>
                            <select aria-label={t('assign')} value={assignTarget[o.id] ?? ''} disabled={busy === o.id}
                                    onChange={e => setAssignTarget(m => ({ ...m, [o.id]: e.target.value }))}>
                              <option value="">{t('assign')}…</option>
                              {containers.map(c => (
                                <option key={c.id} value={c.id}>{c.container_no}</option>
                              ))}
                            </select>
                            <button className="btn small" disabled={busy === o.id || !assignTarget[o.id]}
                                    onClick={() => runAction(o.id, () =>
                                      api.put(`/api/containers/${assignTarget[o.id]}/orders/${o.id}`, {}))}>
                              {t('assign')}
                            </button>
                          </>
                        )}
                        {o.cart_status === 'zablokowane' ? (
                          <button className="btn small secondary" disabled={busy === o.id}
                                  onClick={() => runAction(o.id, () => api.post(`/api/purchase-orders/${o.id}/unblock`, {}))}>
                            {t('unblock')}
                          </button>
                        ) : (
                          <button className="btn small secondary" disabled={busy === o.id}
                                  onClick={() => runAction(o.id, () => api.post(`/api/purchase-orders/${o.id}/block`, {}))}>
                            {t('block')}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel">
        <h2 className="as-h3">{t('containersSection')}</h2>
        {filled.length === 0 ? <EmptyState bare icon={ShoppingCart} title={t('emptyCart')} /> : (
          <div style={{ overflowX: 'auto' }}>
            <table className="grid">
              <thead>
                <tr>
                  <th>{t('containerNo')}</th><th>{t('fillLabel')}</th>
                  <th>CRD</th><th>{t('poContainers')}</th><th><span className="sr-only">{t('actions')}</span></th>
                </tr>
              </thead>
              <tbody>
                {filled.map(containerRow)}
              </tbody>
            </table>
          </div>
        )}
        {empty.length > 0 && (
          <details className="cart-empty" style={{ marginTop: 10 }}>
            <summary>{t('cartEmptyConsolidations').replace('{n}', String(empty.length))}</summary>
            <div style={{ overflowX: 'auto' }}>
              <table className="grid">
                <tbody>{empty.map(containerRow)}</tbody>
              </table>
            </div>
          </details>
        )}
      </div>
    </main>
  )
}
