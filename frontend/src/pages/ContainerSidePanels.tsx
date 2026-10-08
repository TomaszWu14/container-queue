import { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useToast } from '../feedback'
import { useT } from '../i18n'
import type { Container, PurchasingStatus } from '../types'
import { Field } from '../Field'
import { PURCHASING_STATUSES } from '../types'

// Panele prawej kolumny karty kontenera: klient tranzytu, klient (znacznik), zakupy.

// Sekcja klienta docelowego (tranzyt): dane + edycja inline dla admin/logistics.
export function TransitCustomerPanel({ container, canEdit, onSaved }:
  { container: Container; canEdit: boolean; onSaved: (c: Container) => void }) {
  const t = useT()
  const { showToast } = useToast()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(container.customer_name)
  const [address, setAddress] = useState(container.customer_address)
  const [contact, setContact] = useState(container.customer_contact)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const startEdit = () => {
    setName(container.customer_name)
    setAddress(container.customer_address)
    setContact(container.customer_contact)
    setError('')
    setEditing(true)
  }

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const updated = await api.patch<Container>(`/api/containers/${container.id}`,
        { customer_name: name, customer_address: address, customer_contact: contact })
      onSaved(updated)
      setEditing(false)
      showToast(t('toastClientSaved'))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const item = (label: string, value: React.ReactNode) => (
    <div className="item"><b>{label}</b>{value === null || value === undefined || value === '' ? '—' : value}</div>
  )

  return (
    <section className="panel">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>{t('transitCustomer')}</h3>
        {canEdit && !editing && (
          <button className="btn small secondary" onClick={startEdit}>{t('edit')}</button>
        )}
      </div>
      {!editing && (
        <div className="detail-grid">
          {item(t('customerName'), container.customer_name)}
          {item(t('customerAddress'), container.customer_address)}
          {item(t('customerContact'), container.customer_contact)}
        </div>
      )}
      {editing && (
        <div className="detail-grid">
          <div className="item">
            <b>{t('customerName')}</b>
            <input aria-label={t('customerName')} value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div className="item">
            <b>{t('customerAddress')}</b>
            <input aria-label={t('customerAddress')} value={address} onChange={e => setAddress(e.target.value)} />
          </div>
          <div className="item">
            <b>{t('customerContact')}</b>
            <input aria-label={t('customerContact')} value={contact} onChange={e => setContact(e.target.value)} />
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn small" onClick={save} disabled={saving}>
              {saving ? '…' : t('save')}
            </button>
            <button className="btn small secondary" onClick={() => setEditing(false)} disabled={saving}>
              {t('cancel')}
            </button>
          </div>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  )
}

// Panel portalu klienckiego: przypięcie klienta ze słownika + link do portalu
// (wiele kontenerów per klient). Osobno od tekstowych pól tranzytu (customer_*).
type CustomerDict = { id: number; company_id: number; name: string; contact: string }

export function CustomerPortalPanel({ container, onSaved }:
  { container: Container; onSaved: (c: Container) => void }) {
  const t = useT()
  const { showToast } = useToast()
  const [customers, setCustomers] = useState<CustomerDict[]>([])
  const [customerId, setCustomerId] = useState<string>(container.customer_id?.toString() ?? '')
  const [newName, setNewName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get<CustomerDict[]>('/api/customers')
      .then(list => setCustomers(list.filter(c => c.company_id === container.company_id)))
      .catch(() => {})
  }, [container.company_id])
  useEffect(() => { setCustomerId(container.customer_id?.toString() ?? '') },
    [container.customer_id])

  const assign = async (id: number | null) => {
    setBusy(true)
    setError('')
    try {
      await api.put(`/api/containers/${container.id}/customer`, { customer_id: id })
      onSaved({ ...container, customer_id: id })
      showToast(t('saved'))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const addCustomer = async () => {
    if (!newName.trim()) return
    setBusy(true)
    setError('')
    try {
      const created = await api.post<CustomerDict>('/api/customers',
        { name: newName.trim(), company_id: container.company_id })
      setCustomers(cs => [...cs, created])
      setNewName('')
      setCustomerId(String(created.id))
      await assign(created.id)
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <h3 style={{ margin: 0 }}>{t('portalPanel')}</h3>
      <div className="field-row" style={{ marginTop: 8 }}>
        <Field label={t('fieldCustomer')}>
          <select value={customerId} disabled={busy}
                  onChange={e => {
                    setCustomerId(e.target.value)
                    assign(e.target.value ? Number(e.target.value) : null)
                  }}>
            <option value="">— {t('portalNoCustomer')} —</option>
            {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <Field label={t('portalNewCustomer')}>
          <input value={newName} onChange={e => setNewName(e.target.value)} />
        </Field>
        <button className="btn small secondary" onClick={addCustomer}
                disabled={busy || !newName.trim()}
                title={newName.trim() ? undefined : t('hintTypeCustomer')}>{t('add')}</button>
      </div>
      <p style={{ color: 'var(--muted)', fontSize: 13, margin: '6px 0 0' }}>
        {t('portalPanelHint')}
      </p>
      {error && <p className="error">{error}</p>}
    </section>
  )
}

// Panel działu zakupów: jedyne pole, jakie edytuje rola `purchasing` (obok admin/logistics).
export function PurchasingPanel({ container, onSaved }: { container: Container; onSaved: () => void }) {
  const t = useT()
  const [status, setStatus] = useState<PurchasingStatus>(container.purchasing_status)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const save = async () => {
    setSaving(true)
    setError('')
    try {
      await api.put(`/api/purchasing/containers/${container.id}/status`,
                    { purchasing_status: status })
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }
  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>{t('purchasing')}</h3>
        <div className="row" style={{ gap: 8 }}>
          <select aria-label={t('purchasing')} value={status} onChange={e => setStatus(e.target.value as PurchasingStatus)}>
            {PURCHASING_STATUSES.map(s => <option key={s} value={s}>{t(`ps_${s}`)}</option>)}
          </select>
          <button className="btn small" onClick={save}
                  disabled={saving || status === container.purchasing_status}
                  title={status === container.purchasing_status ? t('hintChangeStatus') : undefined}>
            {saving ? '…' : t('save')}
          </button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  )
}
