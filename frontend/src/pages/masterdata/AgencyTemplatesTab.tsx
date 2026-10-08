// Wzory plików dla agencji (2026-10-06): jaki plik agencja przyjmuje — kolumny w kolejności,
// skąd aplikacja bierze dane, które są wymagane, przykład z wzoru agencji. Edycja na wypadek
// zmiany wzoru u agencji; „Wgraj nowy wzór” przejmuje nagłówki z pliku, mapowanie zostaje.
import { ArrowDownIcon, ArrowUpIcon, XIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, downloadFile, errorMessage } from '../../api'
import { useT } from '../../i18n'

export interface TplColumn {
  name: string; source: string; value: string; required: boolean; note: string; example: string
}
export interface AgencyTemplate {
  key: string; name: string; description: string; sheet: string; columns: TplColumn[]; has_sample: boolean
}
interface Payload { sources: Record<string, string>; templates: AgencyTemplate[] }

/** Litera kolumny Excela (0 → A, 26 → AA) — układ jak w pliku agencji. */
export const colLetter = (i: number): string =>
  (i >= 26 ? colLetter(Math.floor(i / 26) - 1) : '') + String.fromCharCode(65 + (i % 26))

const blank = (): TplColumn => ({ name: '', source: 'empty', value: '', required: false, note: '', example: '' })

export default function AgencyTemplatesTab() {
  const t = useT()
  const [data, setData] = useState<Payload | null>(null)
  const [cols, setCols] = useState<TplColumn[]>([])
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const tpl = data?.templates[0] ?? null

  const take = (p: Payload) => { setData(p); setCols(p.templates[0]?.columns ?? []); setDirty(false) }
  useEffect(() => {
    api.get<Payload>('/api/agency-templates')
      .then(p => { if (p && Array.isArray(p.templates)) take(p) }).catch(e => setError(errorMessage(e)))
  }, [])

  const run = async (fn: () => Promise<AgencyTemplate>, done: string) => {
    if (!data) return
    setBusy(true); setError(''); setNote('')
    try {
      const next = await fn()
      take({ ...data, templates: [next] })
      setNote(done)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const save = () => tpl && run(() => api.put<AgencyTemplate>(`/api/agency-templates/${tpl.key}`, { columns: cols }),
    t('atplSaved'))
  const upload = (file: File | null) => file && tpl && run(
    () => api.upload<AgencyTemplate>(`/api/agency-templates/${tpl.key}/sample`, file, 'file'), t('atplSampleSaved'))

  const set = (i: number, patch: Partial<TplColumn>) => {
    setCols(prev => prev.map((c, j) => (j === i ? { ...c, ...patch } : c))); setDirty(true)
  }
  const move = (i: number, d: -1 | 1) => {
    setCols(prev => {
      const next = [...prev]
      ;[next[i], next[i + d]] = [next[i + d], next[i]]
      return next
    }); setDirty(true)
  }
  const remove = (i: number) => { setCols(prev => prev.filter((_, j) => j !== i)); setDirty(true) }

  if (!data || !tpl) return error ? <p className="error">{error}</p> : <p className="muted">…</p>
  const required = cols.filter(c => c.required).length
  return (
    <div className="panel atpl">
      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <h3 style={{ margin: 0 }}>{tpl.name}</h3>
        <div className="row" style={{ gap: 8 }}>
          {tpl.has_sample && (
            <button type="button" className="btn small secondary" disabled={busy}
                    onClick={() => downloadFile(`/api/agency-templates/${tpl.key}/sample`, `wzor_${tpl.key}.xlsx`)
                      .catch(e => setError(errorMessage(e)))}>{t('atplDownload')}</button>
          )}
          <label className="btn small" style={{ cursor: 'pointer' }}>
            {busy ? '…' : t('atplUpload')}
            <input type="file" hidden accept=".xlsx,.xlsm" disabled={busy}
                   onChange={e => { upload(e.target.files?.[0] ?? null); e.target.value = '' }} />
          </label>
        </div>
      </div>
      <p className="muted" style={{ fontSize: 14 }}>{tpl.description}</p>
      <p style={{ fontSize: 13, margin: '0 0 8px' }}>
        <b>{t('atplLayout')}:</b> {t('atplLayoutText').replace('{sheet}', tpl.sheet)
          .replace('{n}', String(cols.length)).replace('{req}', String(required))}
      </p>
      {error && <p className="error">{error}</p>}
      {note && <p className="muted" role="status">{note}</p>}
      <div style={{ overflowX: 'auto' }}>
        <table className="grid atpl-table">
          <thead>
            <tr><th>{t('atplCol')}</th><th>{t('atplName')}</th><th>{t('atplSource')}</th>
                <th>{t('atplRequired')}</th><th>{t('atplExample')}</th><th>{t('atplNote')}</th><th></th></tr>
          </thead>
          <tbody>
            {cols.map((c, i) => (
              <tr key={i} className={c.source === 'empty' && c.required ? 'atpl-gap' : undefined}>
                <td className="mono">{colLetter(i)}</td>
                <td><input aria-label={`${t('atplName')} ${colLetter(i)}`} value={c.name}
                           onChange={e => set(i, { name: e.target.value })} /></td>
                <td><div className="atpl-src">
                  <select aria-label={`${t('atplSource')} ${colLetter(i)}`} value={c.source}
                          onChange={e => set(i, { source: e.target.value })}>
                    {Object.entries(data.sources).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
                  </select>
                  {c.source === 'const' && (
                    <input aria-label={`${t('atplValue')} ${colLetter(i)}`} value={c.value} className="atpl-const"
                           onChange={e => set(i, { value: e.target.value })} />
                  )}
                </div></td>
                <td><input type="checkbox" aria-label={`${t('atplRequired')} ${colLetter(i)}`} checked={c.required}
                           onChange={e => set(i, { required: e.target.checked })} /></td>
                <td className="muted" title={c.example}>{c.example || '—'}</td>
                <td><input aria-label={`${t('atplNote')} ${colLetter(i)}`} value={c.note}
                           onChange={e => set(i, { note: e.target.value })} /></td>
                <td><div className="atpl-actions">
                  <button type="button" className="btn small secondary" aria-label={t('atplUp')} disabled={i === 0}
                          onClick={() => move(i, -1)}><ArrowUpIcon size={14} aria-hidden="true" /></button>
                  <button type="button" className="btn small secondary" aria-label={t('atplDown')}
                          disabled={i === cols.length - 1} onClick={() => move(i, 1)}><ArrowDownIcon size={14} aria-hidden="true" /></button>
                  <button type="button" className="btn small secondary" aria-label={t('delete')}
                          onClick={() => remove(i)}><XIcon size={14} aria-hidden="true" /></button>
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row" style={{ gap: 8, marginTop: 8 }}>
        <button type="button" className="btn small secondary" disabled={busy}
                onClick={() => { setCols(prev => [...prev, blank()]); setDirty(true) }}>{t('atplAdd')}</button>
        <button type="button" className="btn small" disabled={busy || !dirty} onClick={save}>{t('save')}</button>
        {dirty && <span className="muted">{t('atplUnsaved')}</span>}
      </div>
    </div>
  )
}
