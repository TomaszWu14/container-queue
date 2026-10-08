import { FormEvent, useEffect, useMemo, useState } from 'react'
import { api, downloadFile, errorMessage } from '../api'
import { useUser } from '../App'
import { useDicts } from '../components'
import { useT } from '../i18n'
import type { Company, Container } from '../types'
import { useConfirm } from '../ConfirmDialog'
import { FilePicker } from '../FilePicker'

type FreightContainer = { id: number; container_no: string }
type FreightInvoice = {
  id: number; company_id: number; bl_number: string; invoice_number: string
  forwarder_name: string | null; amount: number | null; currency: string; note: string
  filename: string; has_file: boolean; amount_per_container: number | null
  uploaded_by_login: string | null; created_at: string; containers: FreightContainer[]
  status: string; approved_by_login: string | null; approval_note: string
}

// kolor plakietki statusu obiegu akceptacji faktury
const FI_STATUS_CLASS: Record<string, string> = {
  NOWA: 'st-ZAPOWIEDZIANY', DO_AKCEPTACJI: 'st-AWIZOWANY',
  ZAAKCEPTOWANA: 'st-ZREALIZOWANY', ODRZUCONA: 'badge-danger',
}

// Faktury transportowe BL — jedna faktura na zestaw kontenerów (m2m).
// Kanał równoległy do załączników per kontener; wybór wielu kontenerów przy dodawaniu.
export default function FreightInvoicesPanel() {
  const t = useT()
  const { confirm, prompt } = useConfirm()
  const dicts = useDicts()
  const user = useUser()
  const isApprover = user?.role === 'admin'   // rozdzielenie obowiązków: zatwierdza admin
  const [items, setItems] = useState<FreightInvoice[]>([])
  const [companies, setCompanies] = useState<Company[]>([])
  const [containers, setContainers] = useState<Container[]>([])
  const [companyId, setCompanyId] = useState('')
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [search, setSearch] = useState('')
  const [form, setForm] = useState({ bl_number: '', invoice_number: '', forwarder_id: '',
    amount: '', currency: 'EUR', note: '' })
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api.get<FreightInvoice[]>('/api/freight-invoices').then(setItems)
    .catch(err => setError(errorMessage(err)))
  useEffect(() => { load() }, [])
  useEffect(() => {
    api.get<Company[]>('/api/companies').then(cs => {
      setCompanies(cs)
      if (cs.length === 1) setCompanyId(String(cs[0].id))  // jedna spółka → wybrana z automatu
    }).catch(() => {})
    api.get<Container[]>('/api/containers?completed=false&limit=2000').then(setContainers).catch(() => {})
  }, [])

  // kontenery do wyboru: tylko z wybranej spółki (izolacja) + filtr tekstowy
  const options = useMemo(() => containers.filter(c =>
    (!companyId || c.company_id === Number(companyId))
    && (!search || (c.container_no ?? '').toLowerCase().includes(search.toLowerCase()))
  ), [containers, companyId, search])

  const toggle = (id: number) => setPicked(p => {
    const next = new Set(p); next.has(id) ? next.delete(id) : next.add(id); return next
  })

  // zmiana spółki czyści wybór — kontenery innej spółki są niedozwolone
  const changeCompany = (id: string) => { setCompanyId(id); setPicked(new Set()) }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    if (!companyId) { setError(t('blPickCompany')); return }
    if (picked.size === 0) { setError(t('blPickContainers')); return }
    setBusy(true); setError('')
    try {
      const extra: Record<string, string> = {
        company_id: companyId, container_ids: [...picked].join(','),
        bl_number: form.bl_number, invoice_number: form.invoice_number,
        currency: form.currency, note: form.note,
      }
      if (form.forwarder_id) extra.forwarder_id = form.forwarder_id
      if (form.amount) extra.amount = form.amount
      await api.upload('/api/freight-invoices', file ? [file] : [], 'file', extra)
      setForm({ bl_number: '', invoice_number: '', forwarder_id: '', amount: '', currency: 'EUR', note: '' })
      setPicked(new Set()); setFile(null); setSearch('')
      load()
    } catch (err) { setError(errorMessage(err)) }
    finally { setBusy(false) }
  }

  const remove = async (inv: FreightInvoice) => {
    if (!(await confirm(`${t('confirmDeleteEntry')} „${inv.bl_number || inv.invoice_number || inv.id}"?`, { danger: true }))) return
    api.del(`/api/freight-invoices/${inv.id}`).then(load).catch(err => setError(errorMessage(err)))
  }

  // obieg akceptacji (#42): zgłoś do akceptacji / zatwierdź / odrzuć (z powodem)
  const act = (inv: FreightInvoice, verb: string, note?: string) =>
    api.post(`/api/freight-invoices/${inv.id}/${verb}`, note !== undefined ? { note } : {})
      .then(load).catch(err => setError(errorMessage(err)))
  const reject = async (inv: FreightInvoice) => {
    const note = await prompt(t('fiRejectPrompt'))
    if (note === null) return
    act(inv, 'reject', note)
  }

  return (
    <div className="panel">
      <h3>{t('blInvoices')}</h3>
      <form onSubmit={submit} style={{ marginBottom: 16 }}>
        <div className="row" style={{ flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
          {companies.length > 1 && (
            <select aria-label={t('company')} value={companyId} onChange={e => changeCompany(e.target.value)} required>
              <option value="">— {t('company')} —</option>
              {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          )}
          <input aria-label={t('blNumber')} placeholder={t('blNumber')} value={form.bl_number}
                 onChange={e => setForm(f => ({ ...f, bl_number: e.target.value }))} />
          <input aria-label={t('blInvoiceNumber')} placeholder={t('blInvoiceNumber')} value={form.invoice_number}
                 onChange={e => setForm(f => ({ ...f, invoice_number: e.target.value }))} />
          <select aria-label={t('forwarder')} value={form.forwarder_id}
                  onChange={e => setForm(f => ({ ...f, forwarder_id: e.target.value }))}>
            <option value="">— {t('forwarder')} —</option>
            {dicts.forwarders.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          <input type="number" step="0.01" min="0" aria-label={t('blAmount')} placeholder={t('blAmount')} style={{ width: 120 }}
                 value={form.amount} onChange={e => setForm(f => ({ ...f, amount: e.target.value }))} />
          <input aria-label={t('currency')} placeholder={t('currency')} style={{ width: 70 }} value={form.currency}
                 onChange={e => setForm(f => ({ ...f, currency: e.target.value }))} />
          <FilePicker label={t('fieldFile')} file={file} onChange={setFile} />
        </div>
        <input aria-label={t('mdNote')} placeholder={t('mdNote')} value={form.note} style={{ width: '100%', marginBottom: 8 }}
               onChange={e => setForm(f => ({ ...f, note: e.target.value }))} />

        <div className="panel" style={{ padding: 8, marginBottom: 8 }}>
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
            <b>{t('blSelectContainers')} ({picked.size})</b>
            <input aria-label={t('search')} placeholder={t('search')} value={search}
                   onChange={e => setSearch(e.target.value)} style={{ width: 180 }} />
          </div>
          <div style={{ maxHeight: 180, overflowY: 'auto', display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 4 }}>
            {options.map(c => (
              <label key={c.id} className="mono" style={{ display: 'flex', gap: 6, fontSize: 13 }}>
                <input type="checkbox" checked={picked.has(c.id)} onChange={() => toggle(c.id)} />
                {c.container_no}
              </label>
            ))}
            {options.length === 0 && <span className="muted">{t('blNoContainers')}</span>}
          </div>
        </div>

        {error && <p className="error">{error}</p>}
        <button className="btn" disabled={busy}>{t('add')}</button>
      </form>

      <table className="grid">
        <thead>
          <tr>
            <th>{t('blNumber')}</th><th>{t('blInvoiceNumber')}</th><th>{t('forwarder')}</th>
            <th>{t('containers')}</th><th>{t('blAmount')}</th><th>{t('blPerContainer')}</th>
            <th>{t('status')}</th><th></th>
          </tr>
        </thead>
        <tbody>
          {items.map(inv => (
            <tr key={inv.id}>
              <td className="mono">{inv.bl_number || '—'}</td>
              <td className="mono">{inv.invoice_number || '—'}</td>
              <td>{inv.forwarder_name ?? '—'}</td>
              <td title={inv.containers.map(c => c.container_no).join(', ')}>
                {inv.containers.length} · <span className="mono" style={{ fontSize: 12 }}>
                  {inv.containers.slice(0, 3).map(c => c.container_no).join(', ')}
                  {inv.containers.length > 3 ? '…' : ''}
                </span>
              </td>
              <td className="mono">{inv.amount != null ? `${inv.amount} ${inv.currency}` : '—'}</td>
              <td className="mono">{inv.amount_per_container != null
                ? `${inv.amount_per_container} ${inv.currency}` : '—'}</td>
              <td>
                <span className={`badge ${FI_STATUS_CLASS[inv.status] ?? ''}`}
                      title={inv.approval_note || undefined}>
                  {t(`fiStatus_${inv.status}`)}
                </span>
                {inv.status === 'ZAAKCEPTOWANA' && inv.approved_by_login && (
                  <div className="muted" style={{ fontSize: 11 }}>{inv.approved_by_login}</div>
                )}
              </td>
              <td>
                <span className="row">
                  {(inv.status === 'NOWA' || inv.status === 'ODRZUCONA') && (
                    <button className="btn small secondary" onClick={() => act(inv, 'submit')}>
                      {t('fiSubmit')}
                    </button>
                  )}
                  {isApprover && inv.status === 'DO_AKCEPTACJI' && (
                    <>
                      <button className="btn small" onClick={() => act(inv, 'approve')}>{t('fiApprove')}</button>
                      <button className="btn small danger" onClick={() => reject(inv)}>{t('fiReject')}</button>
                    </>
                  )}
                  {inv.has_file && (
                    <button type="button" className="btn small secondary"
                            onClick={() => downloadFile(`/api/freight-invoices/${inv.id}/download`,
                              inv.filename || `BL-${inv.id}`).catch(err => setError(errorMessage(err)))}>
                      {t('download')}
                    </button>
                  )}
                  <button className="btn small danger" onClick={() => remove(inv)}>{t('del')}</button>
                </span>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={8} className="muted" style={{ textAlign: 'center' }}>{t('blNoInvoices')}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
