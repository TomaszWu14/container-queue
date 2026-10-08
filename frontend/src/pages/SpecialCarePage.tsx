import { ShieldCheck } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { EmptyState, LoadError, Skeleton, useToast } from '../feedback'
import { useCompanies } from './admin/shared'
import type { Company } from '../types'
import { formatDate } from '../dates'
import { useConfirm } from '../ConfirmDialog'
import { useUser } from '../userContext'
import { PageHeader } from '../PageHeader'
import { Field } from '../Field'

interface CustomerOrder {
  id: number
  company_id: number
  name: string
  customer_name: string
  order_refs: string
  deadline: string | null
  max_etd: string | null
  buffer_days: number
  responsible_id: number | null
  responsible_name: string | null
  alert_on_delay: boolean
  note: string
  created_at: string
  matched_count: number
  earliest_etd: string | null
  latest_eta: string | null
  departed: boolean
  trigger_etd_missed: boolean
  trigger_forecast_late: boolean
  at_risk: boolean
  matched: { id: number; container_no: string }[]
}

// pusty formularz — jedna definicja dla add i reset po submicie
const emptyForm = {
  name: '', customer_name: '', order_refs: '', deadline: '', max_etd: '',
  buffer_days: '5', responsible_id: '', alert_on_delay: true, note: '', company_id: '',
}

export default function SpecialCarePage() {
  const t = useT()
  const { confirm } = useConfirm()
  const { showToast } = useToast()
  // sprzedaż: tylko podgląd (bez formularza, edycji i list spółek/osób — API zamknięte)
  const readOnly = useUser()?.role === 'sales'
  const companies = useCompanies(!readOnly)
  const [orders, setOrders] = useState<CustomerOrder[]>([])
  const [users, setUsers] = useState<{ id: number; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [onlyAtRisk, setOnlyAtRisk] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [editId, setEditId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState(emptyForm)

  const load = () => {
    setLoading(true); setLoadError('')
    api.get<CustomerOrder[]>('/api/customer-orders')
      .then(setOrders)
      .catch(err => setLoadError(errorMessage(err)))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])
  // lekka lista osób (id + imię i nazwisko) dla admin/logistyki — /api/users zostaje admin-only
  useEffect(() => {
    if (readOnly) return
    api.get<typeof users>('/api/customer-orders/responsibles').then(setUsers).catch(() => setUsers([]))
  }, [readOnly])

  const act = async (fn: () => Promise<unknown>) => {
    if (busy) return
    setBusy(true); setError('')
    try {
      await fn()
      setEditId(null)
      showToast(t('toastSaved'))
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const payload = (f: typeof emptyForm) => ({
    name: f.name,
    customer_name: f.customer_name,
    order_refs: f.order_refs,
    deadline: f.deadline || null,
    max_etd: f.max_etd || null,
    buffer_days: Number(f.buffer_days) || 0,
    responsible_id: f.responsible_id ? Number(f.responsible_id) : null,
    alert_on_delay: f.alert_on_delay,
    note: f.note,
    company_id: f.company_id ? Number(f.company_id) : (companies[0]?.id ?? null),
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    act(async () => {
      await api.post('/api/customer-orders', payload(form))
      setForm(emptyForm)
    })
  }

  const startEdit = (o: CustomerOrder) => {
    setEditId(o.id)
    setEditForm({
      name: o.name, customer_name: o.customer_name, order_refs: o.order_refs,
      deadline: o.deadline ?? '', max_etd: o.max_etd ?? '',
      buffer_days: String(o.buffer_days), responsible_id: o.responsible_id ? String(o.responsible_id) : '',
      alert_on_delay: o.alert_on_delay, note: o.note, company_id: String(o.company_id),
    })
  }

  const saveEdit = (id: number) => act(() => api.patch(`/api/customer-orders/${id}`, payload(editForm)))
  const remove = async (o: CustomerOrder) => {
    if (!(await confirm(`${t('confirmDeleteEntry')} „${o.name}"?`, { danger: true }))) return
    act(() => api.del(`/api/customer-orders/${o.id}`))
  }

  const riskLabel = (o: CustomerOrder) => {
    if (!o.at_risk) return null
    const parts: string[] = []
    if (o.trigger_etd_missed) parts.push(t('careRiskEtd'))
    if (o.trigger_forecast_late) parts.push(t('careRiskForecast'))
    return parts.length ? parts.join(' · ') : t('careRiskEtd')
  }

  const visible = orders.filter(o => !onlyAtRisk || o.at_risk)

  if (loading && orders.length === 0) return <main className="page"><Skeleton rows={6} /></main>
  if (loadError && orders.length === 0)
    return <main className="page"><LoadError message={loadError} onRetry={load} /></main>

  return (
    <main className="page">
      <p className="eyebrow">{t('careEyebrow')}</p>
      <PageHeader title={t('careTitle')} />

      {readOnly ? <p className="muted" style={{ margin: '12px 0' }}>{t('careReadOnlyHint')}</p> : (
      // B26: formularz w karcie, etykiety nad polami w siatce (dawniej placeholdery, etykiety inline
      // i surowy klucz „note”); numery zamówień — pole na 2 kolumny z podpowiedzią separatora
      <form className="panel field-row care-form" onSubmit={submit}>
        <Field label={t('careOrderName')}>
          <input value={form.name} required onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        </Field>
        <Field label={t('careCustomer')}>
          <input value={form.customer_name} required
                 onChange={e => setForm(f => ({ ...f, customer_name: e.target.value }))} />
        </Field>
        <Field label={t('careRefs')} hint={t('careRefsHint')} className="wide">
          <textarea value={form.order_refs} rows={1}
                    onChange={e => setForm(f => ({ ...f, order_refs: e.target.value }))} />
        </Field>
        <Field label={t('careDeadline')}>
          <input type="date" value={form.deadline}
                 onChange={e => setForm(f => ({ ...f, deadline: e.target.value }))} />
        </Field>
        <Field label={t('careMaxEtd')}>
          <input type="date" value={form.max_etd}
                 onChange={e => setForm(f => ({ ...f, max_etd: e.target.value }))} />
        </Field>
        <Field label={t('careBufferDays')}>
          <input type="number" min={0} value={form.buffer_days}
                 onChange={e => setForm(f => ({ ...f, buffer_days: e.target.value }))} />
        </Field>
        {users.length > 0 && (
          <Field label={t('careResponsible')}>
            <select value={form.responsible_id}
                    onChange={e => setForm(f => ({ ...f, responsible_id: e.target.value }))}>
              <option value="">—</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </Field>
        )}
        {companies.length > 1 && (
          <Field label={t('company')}>
            <select value={form.company_id} required
                    onChange={e => setForm(f => ({ ...f, company_id: e.target.value }))}>
              <option value="">—</option>
              {companies.map((c: Company) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
        )}
        <Field label={t('notes')} className="wide">
          <input value={form.note} onChange={e => setForm(f => ({ ...f, note: e.target.value }))} />
        </Field>
        <label className="row check-row">
          <input type="checkbox" checked={form.alert_on_delay}
                 onChange={e => setForm(f => ({ ...f, alert_on_delay: e.target.checked }))} />
          {t('careAlertOnDelay')}
        </label>
        <button className="btn" disabled={busy}>{t('add')}</button>
      </form>
      )}
      {error && <p className="error">{error}</p>}

      <label className="row" style={{ gap: 4, marginBottom: 8 }}>
        <input type="checkbox" checked={onlyAtRisk} onChange={e => setOnlyAtRisk(e.target.checked)} />
        {t('careOnlyAtRisk')}
      </label>

      <div style={{ overflowX: 'auto' }}>
        <table className="grid dict-table">
          <thead>
            <tr>
              <th>{t('careOrderName')}</th>
              <th>{t('careCustomer')}</th>
              <th>{t('careDeadline')}</th>
              <th>{t('careMaxEtd')}</th>
              <th>{t('careMatched')}</th>
              <th>{t('careLatestEta')}</th>
              <th>{t('careRisk')}</th>
              <th><span className="sr-only">{t('actions')}</span></th>
            </tr>
          </thead>
          <tbody>
            {visible.map(o => {
              const risk = riskLabel(o)
              const editing = editId === o.id
              return (
                <tr key={o.id}>
                  <td>{editing
                    ? <input aria-label={t('careOrderName')} value={editForm.name} autoFocus
                             onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))} />
                    : o.name}</td>
                  <td>{editing
                    ? <input aria-label={t('careCustomer')} value={editForm.customer_name}
                             onChange={e => setEditForm(f => ({ ...f, customer_name: e.target.value }))} />
                    : o.customer_name}</td>
                  <td>{editing
                    ? <input aria-label={t('careDeadline')} type="date" value={editForm.deadline}
                             onChange={e => setEditForm(f => ({ ...f, deadline: e.target.value }))} />
                    : formatDate(o.deadline)}</td>
                  <td>{editing
                    ? <input aria-label={t('careMaxEtd')} type="date" value={editForm.max_etd}
                             onChange={e => setEditForm(f => ({ ...f, max_etd: e.target.value }))} />
                    : formatDate(o.max_etd)}</td>
                  <td title={o.matched.map(m => m.container_no).join(', ')}>{o.matched_count}</td>
                  <td>{formatDate(o.latest_eta)}</td>
                  <td>
                    <span className={`badge ${o.at_risk ? 'badge-danger' : 'badge-ok'}`}>
                      {risk ?? t('careOk')}
                    </span>
                  </td>
                  <td>
                    {readOnly ? null : editing ? (
                      <button className="btn small" disabled={busy}
                              onClick={() => saveEdit(o.id)}>{t('save')}</button>
                    ) : (
                      <span className="row">
                        <button className="btn small secondary" onClick={() => startEdit(o)}>
                          {t('edit')}
                        </button>
                        <button className="btn small danger" onClick={() => remove(o)}>
                          {t('del')}
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {visible.length === 0 && <EmptyState icon={ShieldCheck} title={t('careNone')} />}
    </main>
  )
}
