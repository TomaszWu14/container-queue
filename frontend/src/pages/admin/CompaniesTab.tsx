import { FormEvent, useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import type { Company } from '../../types'
import { AddCancel, EditActions, DictTable, dash } from './shared'

export default function CompaniesTab() {
  const t = useT()
  const [companies, setCompanies] = useState<Company[]>([])
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [cc, setCc] = useState('')
  const [editId, setEditId] = useState<number | null>(null)
  const [editCc, setEditCc] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api.get<Company[]>('/api/companies').then(setCompanies).catch(err => setError(errorMessage(err)))
  useEffect(() => { load() }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api.post('/api/companies', { name, code, avizo_cc: cc })
      setName(''); setCode(''); setCc('')
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  // PATCH wymaga pełnego CompanyIn — reszta pól bez zmian
  const saveCc = async (c: Company) => {
    setBusy(true); setError('')
    try {
      await api.patch(`/api/companies/${c.id}`, { name: c.name, code: c.code, is_active: c.is_active, avizo_cc: editCc })
      setEditId(null)
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <h3>{t('companies')}</h3>
      <form className="row" onSubmit={submit} style={{ marginBottom: 12 }}>
        <input aria-label={t('name')} placeholder={t('name')} value={name} required onChange={e => setName(e.target.value)} />
        <input aria-label={t('code')} placeholder={t('code')} value={code} required onChange={e => setCode(e.target.value.toUpperCase())} />
        <input placeholder={t('avizoCc')} title={t('avizoCc')} value={cc} onChange={e => setCc(e.target.value)} />
        <AddCancel dirty={!!(name || code || cc)} onReset={() => { setName(''); setCode(''); setCc('') }} />
        <button className="btn" disabled={busy}>{t('add')}</button>
      </form>
      {error && <p className="error">{error}</p>}
      <DictTable cols={[t('name'), { label: t('code'), width: '140px' },
                        { label: t('active'), width: '90px' }, t('avizoCc'), { width: '110px' }]}>
            {companies.map(c => (
              <tr key={c.id}><td>{c.name}</td><td className="mono">{c.code}</td>
                <td>{c.is_active ? t('yes') : t('no')}</td>
                <td>{editId === c.id
                  ? <input value={editCc} autoFocus aria-label={t('avizoCc')} style={{ width: '100%' }}
                           onChange={e => setEditCc(e.target.value)} />
                  : dash(c.avizo_cc)}</td>
                <td>{editId === c.id
                  ? <EditActions busy={busy} dirty={editCc !== (c.avizo_cc ?? '')}
                                 onSave={() => saveCc(c)} onCancel={() => setEditId(null)} />
                  : <button className="btn small secondary"
                            onClick={() => { setEditId(c.id); setEditCc(c.avizo_cc ?? '') }}>{t('edit')}</button>}
                </td></tr>
            ))}
      </DictTable>
    </div>
  )
}
