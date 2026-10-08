import { FormEvent, useCallback, useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { TemplateButtons } from '../../importTemplate'
import { useT } from '../../i18n'

type Paz = { id: number; produkt: string; sztuk_na_palete: number; updated_at: string }

export default function PazSection() {
  const t = useT()
  const [rows, setRows] = useState<Paz[]>([])
  const [form, setForm] = useState({ produkt: '', sztuk_na_palete: '' })
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => {
    api.get<Paz[]>('/api/paz').then(setRows).catch(e => setMsg(errorMessage(e)))
  }, [])
  useEffect(() => { load() }, [load])

  const add = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    try {
      await api.post('/api/paz', {
        produkt: form.produkt.trim(), sztuk_na_palete: Number(form.sztuk_na_palete),
      })
      setForm({ produkt: '', sztuk_na_palete: '' }); load()
    } catch (e) { setMsg(errorMessage(e)) } finally { setBusy(false) }
  }
  const [skipped, setSkipped] = useState<{ row: number; produkt: string; reason: string }[]>([])
  const importFile = async (file: File) => {
    try {
      const res = await api.upload<{ imported: number; skipped?: typeof skipped }>('/api/paz/import', file)
      setMsg(t('pcImported').replace('{n}', String(res.imported)))
      setSkipped(res.skipped ?? [])
      load()
    } catch (e) { setMsg(errorMessage(e)); setSkipped([]) }
  }

  return (
    <>
      <h2>{t('pcPazTitle')}</h2>
      {msg && <p className="info">{msg}</p>}
      {skipped.length > 0 && (
        <details className="info" style={{ margin: '4px 0' }}>
          <summary>{t('pcImportSkipped')} ({skipped.length})</summary>
          <ul style={{ margin: '6px 0', paddingLeft: 18 }}>
            {skipped.map((s, i) => (
              <li key={i}>wiersz {s.row}: {s.produkt || '—'} — {s.reason}</li>
            ))}
          </ul>
        </details>
      )}
      <form onSubmit={add} style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <input aria-label={t('pcProduct')} placeholder={t('pcProduct')} value={form.produkt}
          onChange={e => setForm(f => ({ ...f, produkt: e.target.value }))} />
        <input type="number" min={1} aria-label={t('pcPazPerPallet')} placeholder={t('pcPazPerPallet')} value={form.sztuk_na_palete}
          onChange={e => setForm(f => ({ ...f, sztuk_na_palete: e.target.value }))} />
        <button className="btn small" type="submit" disabled={busy}>{t('save')}</button>
        <label className="btn small secondary">{t('pcImport')}
          <input type="file" accept=".xlsx,.csv" hidden
            onChange={e => e.target.files?.[0] && importFile(e.target.files[0])} />
        </label>
        <TemplateButtons kinds={['paz']} />
      </form>
      <div style={{ overflowX: 'auto' }}>
        <table className="grid" style={{ minWidth: 720 }}>
          <thead><tr><th>{t('pcProduct')}</th><th>{t('pcPazPerPallet')}</th></tr></thead>
          <tbody>
            {rows.map(p => <tr key={p.id}><td>{p.produkt}</td><td>{p.sztuk_na_palete}</td></tr>)}
          </tbody>
        </table>
      </div>
    </>
  )
}
