import { BanIcon, CircleCheckIcon } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import { AddCancel, DictTable } from './shared'

export default function ProblemsTab() {
  const t = useT()
  const [items, setItems] = useState<{ id: number; name: string; sort_order: number; is_active: boolean }[]>([])
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api.get<typeof items>('/api/problem-types').then(setItems).catch(err => setError(errorMessage(err)))
  useEffect(() => { load() }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api.post('/api/problem-types', { name, sort_order: (items.length + 1) * 10, is_active: true })
      setName(''); load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const toggle = async (item: typeof items[number]) => {
    if (busy) return
    setError('')
    setBusy(true)
    try {
      await api.patch(`/api/problem-types/${item.id}`, { ...item, is_active: !item.is_active })
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <h3>{t('problemTypes')}</h3>
      <p style={{ color: 'var(--muted)', fontSize: 14, marginTop: 0 }}>{t('problemTypesInfo')}</p>
      <form className="row" onSubmit={submit} style={{ marginBottom: 12 }}>
        <input aria-label={t('name')} placeholder={t('name')} value={name} required onChange={e => setName(e.target.value)} />
        <AddCancel dirty={name !== ''} onReset={() => setName('')} />
        <button className="btn" disabled={busy}>{t('add')}</button>
      </form>
      {error && <p className="error">{error}</p>}
      <DictTable cols={[t('name'), { label: t('active'), width: '90px' }, { width: '80px' }]}>
            {items.map(item => (
              <tr key={item.id}>
                <td>{item.name}</td>
                <td>{item.is_active ? t('yes') : t('no')}</td>
                <td><button className="btn small secondary" aria-label={item.is_active ? t('deactivate') : t('activate')} onClick={() => toggle(item)}>
                  {item.is_active ? <BanIcon size={14} /> : <CircleCheckIcon size={14} />}</button></td>
              </tr>
            ))}
      </DictTable>
    </div>
  )
}
