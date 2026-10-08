import { CircleCheckIcon } from 'lucide-react'
import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { TemplateButtons } from '../../importTemplate'
import { useT } from '../../i18n'
import { FilePicker } from '../../FilePicker'

interface CportCounts {
  total: number; new: number; updated: number
  with_coords: number; without_coords: number; duplicate: number
}
interface CportImportResult { dry_run: boolean; counts: CportCounts }

// Import słownika portów kontenerowych (xlsx albo tsv/csv) — master data globalne.
// Upsert po kodzie; współrzędne dopasowywane z bazy UN/LOCODE po stronie serwera.
export default function ContainerPortsImportTab() {
  const t = useT()
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<CportImportResult | null>(null)

  const run = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const body = await api.upload<CportImportResult>(
        '/api/import/container-ports?dry_run=false', file)
      setResult(body)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <h3>{t('cportImportTitle')}</h3>
      <p style={{ color: 'var(--muted)', fontSize: 14, margin: '0 0 12px' }}>
        {t('cportImportHint')}
      </p>
      <div className="row">
        <TemplateButtons kinds={['ports']} />
        <FilePicker label={t('fieldFile')} accept=".xlsx,.xlsm,.tsv,.csv,.txt" disabled={busy} file={file}
                    onChange={f => { setFile(f); setResult(null) }} />
        <button className="btn" disabled={!file || busy} onClick={run}>
          {busy ? t('loading') : t('cportImportBtn')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {result && (
        <p className="import-done">
          <CircleCheckIcon size={14} /> {t('marmNew')}: <b>{result.counts.new}</b>
          {' · '}{t('marmUpdated')}: <b>{result.counts.updated}</b>
          {' · '}{t('cportWithCoords')}: <b>{result.counts.with_coords}</b>
          {' · '}{t('cportWithoutCoords')}: <b>{result.counts.without_coords}</b>
        </p>
      )}
    </div>
  )
}
