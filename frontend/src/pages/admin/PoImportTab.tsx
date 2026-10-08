import { CircleCheckIcon } from 'lucide-react'
import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { TemplateButtons } from '../../importTemplate'
import { useT } from '../../i18n'
import { FilePicker } from '../../FilePicker'

interface PoImportResult { matched: number; skipped: number }

// #42: dopisuje order_numbers do ISTNIEJĄCYCH kontenerów po numerze — nie zakłada
// nowych (import PO nie ma dość danych, żeby bezpiecznie założyć kontener).
export default function PoImportTab() {
  const t = useT()
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<PoImportResult | null>(null)

  const run = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const body = await api.upload<PoImportResult>('/api/containers/import-po', file)
      setResult(body)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel">
      <h3>{t('poImportTitle')}</h3>
      <p style={{ color: 'var(--muted)', fontSize: 14, margin: '0 0 12px' }}>
        {t('poImportHint')}
      </p>
      <div className="row">
        <TemplateButtons kinds={['po']} />
        <FilePicker label={t('fieldFile')} accept=".xlsx,.xlsm" disabled={busy} file={file}
                    onChange={f => { setFile(f); setResult(null) }} />
        <button className="btn" disabled={!file || busy} onClick={run}>
          {busy ? t('loading') : t('poImportBtn')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {result && (
        <p className="import-done">
          <CircleCheckIcon size={14} /> {t('poImportMatched')}: <b>{result.matched}</b> · {t('poImportSkipped')}: <b>{result.skipped}</b>
        </p>
      )}
    </div>
  )
}
