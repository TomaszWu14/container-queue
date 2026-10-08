import { CircleCheckIcon } from 'lucide-react'
import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { TemplateButtons } from '../../importTemplate'
import { useT } from '../../i18n'
import { FilePicker } from '../../FilePicker'

interface DltCounts { rows: number; with_hu: number; produkty: number }
interface DltImportResult { dry_run: boolean; counts: DltCounts }

// Import stanów DLT z xlsx — snapshot (każdy import zastępuje poprzedni).
// Fallback dla analityki wywołań, gdy Power BI nie podaje stanów DLT.
export default function DltStockImportTab() {
  const t = useT()
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<DltImportResult | null>(null)

  const run = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const body = await api.upload<DltImportResult>(
        '/api/import/dlt-stock?dry_run=false', file)
      setResult(body)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <h3>{t('dltImportTitle')}</h3>
      <p style={{ color: 'var(--muted)', fontSize: 14, margin: '0 0 12px' }}>
        {t('dltImportHint')}
      </p>
      <div className="row">
        <TemplateButtons kinds={['dlt']} />
        <FilePicker label={t('fieldFile')} accept=".xlsx,.xlsm" disabled={busy} file={file}
                    onChange={f => { setFile(f); setResult(null) }} />
        <button className="btn" disabled={!file || busy} onClick={run}>
          {busy ? t('loading') : t('dltImportBtn')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {result && (
        <p className="import-done">
          <CircleCheckIcon size={14} /> {t('dltRows')}: <b>{result.counts.rows}</b>
          {' · '}{t('dltProdukty')}: <b>{result.counts.produkty}</b>
          {' · '}HU: <b>{result.counts.with_hu}</b>
        </p>
      )}
    </div>
  )
}
