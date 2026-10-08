import { XIcon } from 'lucide-react'
// #12 — słownik mapowań: kod artykułu dostawcy → nasz ref_code (używany przy dopasowaniu faktur).
import { FormEvent, useEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useUser } from '../../App'
import { useT } from '../../i18n'
import { useConfirm } from '../../ConfirmDialog'
import { useBusy } from '../../useBusy'
import type { Company, Supplier } from '../../types'

interface MapRow {
  id: number; company_id: number; supplier_id: number
  supplier_code: string; ref_code: string; note: string
}

const EMPTY = { company_code: '', supplier_id: '', supplier_code: '', ref_code: '', note: '' }

export default function SupplierMapsTab({ companies }: { companies: Company[] }) {
  const t = useT()
  const { confirm } = useConfirm()
  const role = useUser()?.role
  const canEdit = role === 'admin' || role === 'logistics' || role === 'purchasing'
  const [rows, setRows] = useState<MapRow[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [q, setQ] = useState('')
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState('')

  // numer żądania: odpowiedź starszego wyszukiwania (Enter, Enter…) nie nadpisze nowszego
  const seq = useRef(0)
  const load = () => {
    const my = ++seq.current
    return api.get<MapRow[]>(`/api/supplier-material-maps${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''}`)
      .then(r => { if (my === seq.current) setRows(Array.isArray(r) ? r : []) })
      .catch(e => { if (my === seq.current) setError(errorMessage(e)) })
  }
  useEffect(() => {
    load()
    api.get<Supplier[]>('/api/suppliers').then(r => setSuppliers(Array.isArray(r) ? r : [])).catch(() => {})
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  const supplierName = (id: number) => suppliers.find(s => s.id === id)?.name ?? `#${id}`
  const companyCode = (id: number) => companies.find(c => c.id === id)?.code ?? `#${id}`

  const { busy, run } = useBusy()   // Enter+klik / dwuklik „Dodaj” = jedno mapowanie
  const add = (e: FormEvent) => {
    e.preventDefault()
    setError('')
    void run(() => api.post('/api/supplier-material-maps', { ...form, supplier_id: Number(form.supplier_id) })
      .then(() => { setForm(EMPTY); load() }).catch(err => setError(errorMessage(err))))
  }
  // audyt S3: usunięcie mapowania dotąd szło jednym kliknięciem
  const remove = async (r: MapRow) => {
    if (!(await confirm(`${t('confirmDeleteEntry')} „${r.supplier_code} → ${r.ref_code}"?`, { danger: true }))) return
    api.del(`/api/supplier-material-maps/${r.id}`).then(load).catch(err => setError(errorMessage(err)))
  }
  const set = (k: keyof typeof EMPTY) =>
    (e: { target: { value: string } }) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <div className="panel">
      <h3>{t('smapTitle')}</h3>
      <p className="muted">{t('smapHint')}</p>
      {canEdit && (
        <form className="row" style={{ marginBottom: 12 }} onSubmit={add}>
          <select aria-label={t('company')} required value={form.company_code} onChange={set('company_code')}>
            <option value="">{t('company')}</option>
            {companies.map(c => <option key={c.id} value={c.code}>{c.name}</option>)}
          </select>
          <select aria-label={t('supplier')} required value={form.supplier_id} onChange={set('supplier_id')}>
            <option value="">{t('supplier')}</option>
            {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <input required aria-label={t('smapSupplierCode')} placeholder={t('smapSupplierCode')} value={form.supplier_code} onChange={set('supplier_code')} />
          <input required aria-label={t('smapRefCode')} placeholder={t('smapRefCode')} value={form.ref_code} onChange={set('ref_code')} />
          <input aria-label={t('notes')} placeholder={t('notes')} value={form.note} onChange={set('note')} />
          <button className="btn" disabled={busy}>{t('add')}</button>
        </form>
      )}
      <div className="row" style={{ marginBottom: 8 }}>
        <input aria-label={t('mdSearch')} placeholder={t('mdSearch')} value={q} onChange={e => setQ(e.target.value)}
               onKeyDown={e => { if (e.key === 'Enter') load() }} />
      </div>
      {error && <p className="error">{error}</p>}
      <table className="grid">
        <thead><tr>
          <th>{t('company')}</th><th>{t('supplier')}</th><th>{t('smapSupplierCode')}</th>
          <th>{t('smapRefCode')}</th><th>{t('notes')}</th>{canEdit && <th />}
        </tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id}>
              <td>{companyCode(r.company_id)}</td><td>{supplierName(r.supplier_id)}</td>
              <td className="mono">{r.supplier_code}</td><td className="mono">{r.ref_code}</td>
              <td>{r.note}</td>
              {canEdit && <td><button className="btn small secondary" aria-label={t('delete')} onClick={() => remove(r)}><XIcon size={14} /></button></td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
