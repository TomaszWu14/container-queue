import { FormEvent, useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import type { Named } from '../../types'
import { AddCancel, EditActions, DictTable, dash } from './shared'
import { useConfirm } from '../../ConfirmDialog'

type Agency = Named & { contact_person?: string; contact_phone?: string
  address?: string; note?: string }

const EXTRA: { key: 'contact_person' | 'contact_phone' | 'address' | 'note'; labelKey: string }[] = [
  { key: 'contact_person', labelKey: 'mdContact' },
  { key: 'contact_phone', labelKey: 'mdPhone' },
  { key: 'address', labelKey: 'mdAddress' },
  { key: 'note', labelKey: 'mdNote' },
]

// Rejestr agencji celnych — nazwa/e-mail + dane kontaktowe (osoba, telefon, adres, notatka).
export default function CustomsAgenciesTab() {
  const t = useT()
  const { confirm } = useConfirm()
  const [items, setItems] = useState<Agency[]>([])
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [extra, setExtra] = useState<Record<string, string>>({})
  const [editId, setEditId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editExtra, setEditExtra] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api.get<Agency[]>('/api/customs-agencies').then(setItems)
    .catch(err => setError(errorMessage(err)))
  useEffect(() => { load() }, [])

  const act = async (fn: () => Promise<unknown>) => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await fn()
      setEditId(null)
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    act(async () => {
      await api.post('/api/customs-agencies', { name, email, ...extra })
      setName(''); setEmail(''); setExtra({})
    })
  }

  return (
    <div className="panel">
      <h3>{t('customsAgencies')}</h3>
      <form className="row" onSubmit={submit} style={{ marginBottom: 12 }}>
        <input aria-label={t('name')} placeholder={t('name')} value={name} required onChange={e => setName(e.target.value)} />
        <input type="email" aria-label={t('email')} placeholder={t('email')} value={email}
               onChange={e => setEmail(e.target.value)} />
        {EXTRA.map(f => (
          <input key={f.key} aria-label={t(f.labelKey)} placeholder={t(f.labelKey)} value={extra[f.key] ?? ''}
                 onChange={e => setExtra(x => ({ ...x, [f.key]: e.target.value }))} />
        ))}
        <AddCancel dirty={!!(name || email || Object.values(extra).some(Boolean))}
                   onReset={() => { setName(''); setEmail(''); setExtra({}) }} />
        <button className="btn" disabled={busy}>{t('add')}</button>
      </form>
      {error && <p className="error">{error}</p>}
      <DictTable cols={[t('name'), t('email'), ...EXTRA.map(f => t(f.labelKey)),
                        { label: t('active'), width: '90px' }, { width: '110px' }]}>
            {items.map(item => (
              <tr key={item.id} className={item.is_active === false ? 'muted' : ''}>
                <td>
                  {editId === item.id
                    ? <input aria-label={t('name')} value={editName} autoFocus onChange={e => setEditName(e.target.value)} />
                    : item.name}
                </td>
                <td>
                  {editId === item.id
                    ? <input aria-label={t('email')} type="email" value={editEmail} onChange={e => setEditEmail(e.target.value)} />
                    : dash(item.email)}
                </td>
                {EXTRA.map(f => (
                  <td key={f.key}>
                    {editId === item.id
                      ? <input aria-label={t(f.labelKey)} value={editExtra[f.key] ?? ''}
                               onChange={e => setEditExtra(x => ({ ...x, [f.key]: e.target.value }))} />
                      : dash(item[f.key])}
                  </td>
                ))}
                <td>
                  {/* spread ...item zachowuje pola kontaktowe (backend nadpisuje całym model_dump) */}
                  <input type="checkbox" checked={item.is_active !== false} aria-label={t('active')}
                         onChange={e => act(() => api.patch(`/api/customs-agencies/${item.id}`,
                           { ...item, is_active: e.target.checked }))} />
                </td>
                <td>
                  {editId === item.id ? (
                    <EditActions busy={busy} onCancel={() => setEditId(null)}
                                 dirty={editName !== item.name || editEmail !== (item.email ?? '')
                                   || EXTRA.some(f => (editExtra[f.key] ?? '') !== (item[f.key] ?? ''))}
                                 onSave={() => act(() => api.patch(
                                   `/api/customs-agencies/${item.id}`,
                                   { ...item, name: editName, email: editEmail, is_active: item.is_active !== false,
                                     ...editExtra }))} />
                  ) : (
                    <>
                      <button className="btn small secondary" onClick={() => {
                        setEditId(item.id); setEditName(item.name); setEditEmail(item.email ?? '')
                        setEditExtra(Object.fromEntries(EXTRA.map(f => [f.key, item[f.key] ?? ''])))
                      }}>{t('edit')}</button>
                      {/* usunięcie strzeżone backendem (409 gdy agencja w użyciu — konta/kontenery/szablony) */}
                      <button className="btn small danger" onClick={async () =>
                        (await confirm(`${t('confirmDeleteEntry')} „${item.name}"?`, { danger: true }))
                          && act(() => api.del(`/api/customs-agencies/${item.id}`))}>
                        {t('delete')}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
      </DictTable>
    </div>
  )
}
