import { FormEvent, useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import { AddCancel, EditActions, DictTable, dash, useCompanies } from './shared'
import { useConfirm } from '../../ConfirmDialog'

type Customer = { id: number; company_id: number; name: string; contact?: string }

// Słownik klientów portalu (per spółka). Nazwa + kontakt; spółka wybierana przy
// dodawaniu (edycja jej nie zmienia — przeniosłoby klienta poza izolację).
// Usuwanie strzeżone backendem (409 gdy klient ma kontenery lub aktywny link).
export default function CustomersTab() {
  const t = useT()
  const { confirm } = useConfirm()
  const companies = useCompanies()
  const [items, setItems] = useState<Customer[]>([])
  const [name, setName] = useState('')
  const [contact, setContact] = useState('')
  const [companyId, setCompanyId] = useState('')
  const [editId, setEditId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editContact, setEditContact] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api.get<Customer[]>('/api/customers').then(setItems)
    .catch(err => setError(errorMessage(err)))
  useEffect(() => { load() }, [])

  const act = async (fn: () => Promise<unknown>) => {
    if (busy) return
    setBusy(true); setError('')
    try { await fn(); setEditId(null); load() }
    catch (err) { setError(errorMessage(err)) }
    finally { setBusy(false) }
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    act(async () => {
      await api.post('/api/customers', { name, contact, company_id: Number(companyId) })
      setName(''); setContact(''); setCompanyId('')
    })
  }

  const companyName = (id: number) => companies.find(c => c.id === id)?.name ?? dash(null)

  return (
    <div className="panel">
      <h3>{t('customers')}</h3>
      <form className="row" onSubmit={submit} style={{ marginBottom: 12 }}>
        <input aria-label={t('name')} placeholder={t('name')} value={name} required onChange={e => setName(e.target.value)} />
        <input aria-label={t('customerContact')} placeholder={t('customerContact')} value={contact}
               onChange={e => setContact(e.target.value)} />
        <select aria-label={t('company')} value={companyId} required onChange={e => setCompanyId(e.target.value)}>
          <option value="">— {t('company')} —</option>
          {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <AddCancel dirty={!!(name || contact || companyId)} onReset={() => { setName(''); setContact(''); setCompanyId('') }} />
        <button className="btn" disabled={busy}>{t('add')}</button>
      </form>
      {error && <p className="error">{error}</p>}
      <DictTable cols={[t('name'), t('customerContact'), t('company'), { width: '160px' }]}>
        {items.map(item => (
          <tr key={item.id}>
            <td>
              {editId === item.id
                ? <input aria-label={t('name')} value={editName} autoFocus onChange={e => setEditName(e.target.value)} />
                : item.name}
            </td>
            <td>
              {editId === item.id
                ? <input aria-label={t('customerContact')} value={editContact} onChange={e => setEditContact(e.target.value)} />
                : dash(item.contact)}
            </td>
            <td>{companyName(item.company_id)}</td>
            <td>
              {editId === item.id ? (
                <EditActions busy={busy} dirty={editName !== item.name || editContact !== (item.contact ?? '')}
                             onCancel={() => setEditId(null)}
                             onSave={() => act(() => api.patch(
                               `/api/customers/${item.id}`, { name: editName, contact: editContact }))} />
              ) : (
                <span className="row">
                  <button className="btn small secondary" onClick={() => {
                    setEditId(item.id); setEditName(item.name); setEditContact(item.contact ?? '')
                  }}>{t('edit')}</button>
                  <button className="btn small danger" onClick={async () =>
                    (await confirm(`${t('confirmDeleteEntry')} „${item.name}"?`, { danger: true }))
                      && act(() => api.del(`/api/customers/${item.id}`))}>
                    {t('del')}
                  </button>
                </span>
              )}
            </td>
          </tr>
        ))}
      </DictTable>
    </div>
  )
}
