// Dane materiałowe SharePoint (2026-09-29): jeden plik SAP_Dane_materiałowe.xlsm → każda
// zakładka jako osobna tabela (przełączniki u góry); import aktualizuje też nazwy PL i CN
// materiałów (krótka nazwa PL z „Hierarchii produktów”).
import { CircleCheckIcon } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../../api'
import { FilePicker } from '../../FilePicker'
import { formatDate } from '../../dates'
import { useT } from '../../i18n'

interface Sheet { name: string; rows: number; filename: string; imported_at: string | null }
interface Table { headers: string[]; total: number; rows: (string | number)[][] }
interface ImportStatus {
  status: 'none' | 'running' | 'done' | 'error'; filename?: string; error?: string
  counts?: { sheets?: { name: string; rows: number }[]; materials_new?: number; materials_updated?: number }
}

const PAGE = 100
const POLL_MS = 3000   // import w tle: pełny plik to kilkadziesiąt sekund na serwerze

export default function SpMaterialsTab() {
  const t = useT()
  const [sheets, setSheets] = useState<Sheet[]>([])
  const [active, setActive] = useState('')
  const [table, setTable] = useState<Table | null>(null)
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [job, setJob] = useState<ImportStatus | null>(null)

  const loadSheets = useCallback(() => api.get<Sheet[]>('/api/sp-materials/sheets').then(list => {
    setSheets(list)
    setActive(a => (list.some(s => s.name === a) ? a : list[0]?.name ?? ''))
  }).catch(err => setError(errorMessage(err))), [])
  useEffect(() => { loadSheets() }, [loadSheets])

  // stan importu: przy wejściu (import mógł ruszyć wcześniej) i co POLL_MS, dopóki trwa;
  // przejście running → done przeładowuje zakładki
  const wasRunning = useRef(false)
  const check = useCallback(() => api.get<ImportStatus>('/api/sp-materials/import-status').then(s => {
    if (wasRunning.current && s.status === 'done') { setOffset(0); loadSheets() }
    wasRunning.current = s.status === 'running'
    setJob(s)
  }).catch(() => { /* chwilowy błąd sieci — kolejna próba za POLL_MS */ }), [loadSheets])
  useEffect(() => { check() }, [check])
  const running = job?.status === 'running'
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(check, POLL_MS)
    return () => window.clearInterval(timer)
  }, [running, check])

  useEffect(() => {
    if (!active) { setTable(null); return }
    let live = true
    const params = new URLSearchParams({ q, limit: String(PAGE), offset: String(offset) })
    api.get<Table>(`/api/sp-materials/sheets/${encodeURIComponent(active)}?${params}`)
      .then(data => { if (live) setTable(data) })
      .catch(err => { if (live) setError(errorMessage(err)) })
    return () => { live = false }
  }, [active, q, offset])

  const run = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const started = await api.upload<ImportStatus>('/api/import/sp-materials?dry_run=false', file)
      wasRunning.current = started.status === 'running'
      setJob(started)
      if (started.status === 'done') { setOffset(0); await loadSheets() }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const current = sheets.find(s => s.name === active)
  return (
    <div className="panel">
      <h3>{t('spMatTitle')}</h3>
      <p className="muted" style={{ margin: '0 0 12px' }}>{t('spMatHint')}</p>
      <div className="row">
        <FilePicker label={t('fieldFile')} accept=".xlsx,.xlsm" disabled={busy} file={file}
                    onChange={f => setFile(f)} />
        <button className="btn" disabled={!file || busy || running} onClick={run}>
          {busy ? t('spMatUploading') : t('spMatImport')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {running && <p className="muted" role="status">{t('spMatRunning').replace('{file}', job?.filename ?? '')}</p>}
      {job?.status === 'error' && <p className="error">{job.error}</p>}
      {job?.status === 'done' && job.counts && (
        <p className="import-done">
          <CircleCheckIcon size={14} /> {job.filename} · {t('spMatSheets')}: <b>{job.counts.sheets?.length ?? 0}</b>
          {' · '}{t('marmMaterialsNew')}: <b>{job.counts.materials_new ?? 0}</b>
          {' · '}{t('spMatUpdated')}: <b>{job.counts.materials_updated ?? 0}</b>
        </p>
      )}
      {sheets.length === 0 ? <p className="muted">{t('spMatEmpty')}</p> : (
        <>
          <div className="tabs" role="tablist" aria-label={t('spMatTitle')}>
            {sheets.map(s => (
              <button key={s.name} role="tab" aria-selected={s.name === active}
                      className={s.name === active ? 'active' : ''}
                      onClick={() => { setActive(s.name); setOffset(0); setQ('') }}>
                {s.name} <span className="muted">({s.rows})</span>
              </button>
            ))}
          </div>
          <div className="row" style={{ margin: '8px 0' }}>
            <input type="search" value={q} placeholder={t('spMatSearch')} aria-label={t('spMatSearch')}
                   onChange={e => { setQ(e.target.value); setOffset(0) }} />
            {current?.imported_at && (
              <span className="muted txt-sm">
                {current.filename} · {formatDate(current.imported_at)}
              </span>
            )}
          </div>
          {table && (
            <>
              <div className="table-scroll">
                <table className="grid">
                  <thead><tr>{table.headers.map((h, i) => <th key={i}>{h || '—'}</th>)}</tr></thead>
                  <tbody>
                    {table.rows.map((row, r) => (
                      <tr key={offset + r}>{row.map((c, i) => <td key={i}>{String(c)}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="row" style={{ marginTop: 8 }}>
                <span className="muted txt-sm">
                  {table.total === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE, table.total)} / {table.total}
                </span>
                <button className="btn small secondary" disabled={offset === 0}
                        onClick={() => setOffset(o => Math.max(0, o - PAGE))}>{t('spMatPrev')}</button>
                <button className="btn small secondary" disabled={offset + PAGE >= table.total}
                        onClick={() => setOffset(o => o + PAGE)}>{t('spMatNext')}</button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
