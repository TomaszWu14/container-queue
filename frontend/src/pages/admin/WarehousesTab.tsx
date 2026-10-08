import { MapPinIcon } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import { Field } from '../../Field'
import type { Warehouse } from '../../types'
import { DictTable, dash, useCompanies } from './shared'

type WhRow = Warehouse & { email?: string; address?: string; contact_phone?: string
  entry_instructions?: string }

const EMPTY_FORM = { name: '', company_id: '', country: 'PL', default_daily_limit: 7, email: '' }
const EMPTY_EDIT = { default_daily_limit: 7, email: '', address: '', contact_phone: '', entry_instructions: '',
  slot_windows: '', slot_capacity: 1 }

export default function WarehousesTab() {
  const t = useT()
  const companies = useCompanies()
  const [items, setItems] = useState<Warehouse[]>([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [editId, setEditId] = useState<number | null>(null)
  const [edit, setEdit] = useState(EMPTY_EDIT)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const load = () => api.get<Warehouse[]>('/api/warehouses').then(setItems).catch(err => setError(errorMessage(err)))
  useEffect(() => { load() }, [])

  const formDirty = JSON.stringify(form) !== JSON.stringify(EMPTY_FORM)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    setError('')
    try {
      await api.post('/api/warehouses', {
        ...form,
        company_id: form.company_id ? Number(form.company_id) : null,
      })
      setForm(EMPTY_FORM)
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const startEdit = (w: Warehouse) => {
    const row = w as WhRow
    setError('')
    setEditId(w.id)
    setEdit({ default_daily_limit: w.default_daily_limit, email: row.email ?? '', address: row.address ?? '',
      contact_phone: row.contact_phone ?? '', entry_instructions: row.entry_instructions ?? '',
      slot_windows: w.slot_windows ?? '', slot_capacity: w.slot_capacity ?? 1 })
  }

  const saveEdit = async (w: Warehouse) => {
    if (saving) return
    setError('')
    setSaving(true)
    try {
      await api.patch(`/api/warehouses/${w.id}`, { name: w.name, country: w.country, ...edit })
      setEditId(null)
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const companyName = (id: number) => companies.find(c => c.id === id)?.name ?? ''

  return (
    <div className="panel">
      <h3>{t('warehouses')}</h3>
      <form className="row" onSubmit={submit} style={{ marginBottom: 12 }}>
        <input aria-label={t('name')} placeholder={t('name')} value={form.name} required
               onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        <select aria-label={t('company')} value={form.company_id} onChange={e => setForm(f => ({ ...f, company_id: e.target.value }))}>
          <option value="">— {t('company')} —</option>
          {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select aria-label={t('country')} value={form.country} onChange={e => setForm(f => ({ ...f, country: e.target.value }))}>
          <option value="PL">PL</option>
          <option value="PT">PT</option>
        </select>
        <input type="number" min={0} style={{ width: 90 }} title={t('dailyLimit')}
               value={form.default_daily_limit}
               onChange={e => setForm(f => ({ ...f, default_daily_limit: Number(e.target.value) }))} />
        <input type="email" aria-label={t('email')} placeholder={t('email')} value={form.email}
               onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
        <button className="btn" disabled={saving}>{t('add')}</button>
        {formDirty && (
          <button type="button" className="btn secondary" onClick={() => setForm(EMPTY_FORM)}>{t('cancel')}</button>
        )}
      </form>
      {error && <p className="error">{error}</p>}
      <DictTable cols={[t('name'), t('company'), { label: t('country'), width: '110px' },
                        { label: t('dailyLimit'), width: '110px' },
                        { label: t('email'), width: '300px' }, { width: '100px' }]}>
            {items.map(w => (
              <tr key={w.id}>
                <td>{w.name}</td><td>{companyName(w.company_id)}</td>
                <td>{w.country}</td>
                <td>
                  {editId === w.id ? (
                    <input type="number" min={0} style={{ width: 70 }} aria-label={t('dailyLimit')}
                           value={edit.default_daily_limit}
                           onChange={e => setEdit(x => ({ ...x, default_daily_limit: Number(e.target.value) }))} />
                  ) : w.default_daily_limit}
                </td>
                <td>
                  {editId === w.id ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <Field label={t('email')}>
                        <input type="email" value={edit.email} autoFocus
                               onChange={e => setEdit(x => ({ ...x, email: e.target.value }))} />
                      </Field>
                      <Field label={t('whAddress')}>
                        <input value={edit.address} onChange={e => setEdit(x => ({ ...x, address: e.target.value }))} />
                      </Field>
                      <Field label={t('whContactPhone')}>
                        <input value={edit.contact_phone}
                               onChange={e => setEdit(x => ({ ...x, contact_phone: e.target.value }))} />
                      </Field>
                      <Field label={t('whEntryInstructions')}>
                        <textarea rows={2} value={edit.entry_instructions}
                                  onChange={e => setEdit(x => ({ ...x, entry_instructions: e.target.value }))} />
                      </Field>
                      {/* #13 sloty awizacji: puste = wyłączone (spedycja wpisuje tylko datę) */}
                      <Field label={t('whSlots')}>
                        <input value={edit.slot_windows} placeholder="07:00,09:00"
                               onChange={e => setEdit(x => ({ ...x, slot_windows: e.target.value }))} />
                      </Field>
                      <Field label={t('whSlotCap')}>
                        <input type="number" min={1} max={50} style={{ width: 70 }} value={edit.slot_capacity}
                               onChange={e => setEdit(x => ({ ...x, slot_capacity: Number(e.target.value) || 1 }))} />
                      </Field>
                    </div>
                  ) : (
                    <>
                      {dash((w as WhRow).email)}
                      {(w as WhRow).address && (
                        <div style={{ fontSize: 12, color: 'var(--muted)' }}><MapPinIcon size={14} /> {(w as WhRow).address}</div>
                      )}
                      {w.slot_windows && (
                        <div className="mono" style={{ fontSize: 12, color: 'var(--muted)' }}>
                          {t('avizoSlot')}: {w.slot_windows} ×{w.slot_capacity ?? 1}
                        </div>
                      )}
                    </>
                  )}
                </td>
                <td>
                  {editId === w.id ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <button className="btn small" disabled={saving} onClick={() => saveEdit(w)}>{t('save')}</button>
                      <button className="btn small secondary" disabled={saving}
                              onClick={() => { setEditId(null); setError('') }}>{t('cancel')}</button>
                    </div>
                  ) : (
                    <button className="btn small secondary" onClick={() => startEdit(w)}>{t('edit')}</button>
                  )}
                </td>
              </tr>
            ))}
      </DictTable>
    </div>
  )
}
