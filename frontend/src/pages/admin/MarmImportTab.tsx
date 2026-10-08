import { CircleCheckIcon } from 'lucide-react'
import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { TemplateButtons } from '../../importTemplate'
import { useT } from '../../i18n'
import { SapSource } from '../../SapSource'
import { ImportErrors, type ImportRowError } from '../ImportErrors'
import { FilePicker } from '../../FilePicker'

interface MarmCounts {
  total: number; new: number; updated: number; placeholders: number; duplicate: number
  materials_new?: number; conversions?: number
}
interface MarmImportResult { dry_run: boolean; counts: MarmCounts; errors?: ImportRowError[] }

// Import MARM (przeliczniki jednostek materiałów z SAP) — master data globalne.
// Upsert po (materiał, jednostka); placeholdery (jednostka „0") pomijane.
export default function MarmImportTab() {
  const t = useT()
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<MarmImportResult | null>(null)

  const run = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const body = await api.upload<MarmImportResult>(
        '/api/import/material-units?dry_run=false', file)
      setResult(body)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <h3>{t('marmImportTitle')} <SapSource table="MARM" /></h3>
      <p style={{ color: 'var(--muted)', fontSize: 14, margin: '0 0 12px' }}>
        {t('marmImportHint')}
      </p>
      <div className="row">
        <TemplateButtons kinds={['marm']} />
        <FilePicker label={t('fieldFile')} accept=".xlsx,.xlsm" disabled={busy} file={file}
                    onChange={f => { setFile(f); setResult(null) }} />
        <button className="btn" disabled={!file || busy} onClick={run}>
          {busy ? t('loading') : t('marmImportBtn')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {result && (
        <p className="import-done">
          <CircleCheckIcon size={14} /> {t('marmNew')}: <b>{result.counts.new}</b>
          {' · '}{t('marmUpdated')}: <b>{result.counts.updated}</b>
          {' · '}{t('marmPlaceholders')}: <b>{result.counts.placeholders}</b>
          {' · '}{t('marmMaterialsNew')}: <b>{result.counts.materials_new ?? 0}</b>
          {' · '}{t('marmConversions')}: <b>{result.counts.conversions ?? 0}</b>
        </p>
      )}
      {result && <ImportErrors errors={result.errors} />}
    </div>
  )
}
