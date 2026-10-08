import { CircleCheckIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { formatDate } from '../dates'
import { Modal } from '../components'
import { useT } from '../i18n'
import { FilePicker } from '../FilePicker'

// Lekki modal upload z podglądem (dry-run) → zapis. Obsługuje dwa kształty odpowiedzi:
//  - ETD (/import/purchase-orders): { counts: {total,new,updated,linked,duplicate} }
//  - queue-sync (/import/queue-sync): { containers, changed, skipped_old }
interface UploadResult {
  dry_run: boolean
  counts?: { total?: number; new?: number; updated?: number; linked?: number; duplicate?: number }
  containers?: number
  changed?: number
  skipped_old?: number
}

export default function SyncUploadModal({ companyCode, endpoint, titleKey, hintKey, onDone, onClose }: {
  companyCode: string
  endpoint: string
  titleKey: string
  hintKey: string
  onDone: () => void
  onClose: () => void
}) {
  const t = useT()
  const isQueueSync = endpoint === '/api/import/queue-sync'
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<UploadResult | null>(null)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [dateFrom, setDateFrom] = useState('')

  useEffect(() => {
    if (!isQueueSync || !companyCode) return
    api.get<{ date_from: string | null }>(
      `/api/import/queue-sync-date-from?company_code=${encodeURIComponent(companyCode)}`)
      .then(r => setDateFrom(r.date_from ?? ''))
      .catch(() => {})
  }, [isQueueSync, companyCode])

  const run = async (dryRun: boolean) => {
    if (!file) return
    setBusy(true); setError('')
    try {
      const dateFromQ = isQueueSync && dateFrom ? `&date_from=${dateFrom}` : ''
      const body = await api.upload<UploadResult>(
        `${endpoint}?company_code=${encodeURIComponent(companyCode)}&dry_run=${dryRun}${dateFromQ}`, file)
      if (dryRun) setPreview(body)
      else { setResult(body); onDone() }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  // liczba pozycji, którą zatwierdzi commit (0 → przycisk zablokowany)
  const commitCount = (r: UploadResult) =>
    r.counts ? (r.counts.new ?? 0) + (r.counts.updated ?? 0) : (r.changed ?? 0)

  const Summary = ({ r }: { r: UploadResult }) => (
    <div className="import-counts">
      {r.counts ? <>
        <span className="badge st-DOSTARCZONY">{r.counts.new} {t('importNew')}</span>
        <span className="badge st-W_TRANSPORCIE">{r.counts.updated} {t('importUpdated')}</span>
        <span className="badge st-ZREALIZOWANY">{r.counts.linked} {t('importLinked')}</span>
        {(r.counts.duplicate ?? 0) > 0 &&
          <span className="badge st-ODPRAWA">{r.counts.duplicate} {t('importDuplicate')}</span>}
      </> : <>
        <span className="badge st-DOSTARCZONY">{r.containers} {t('queueContainers')}</span>
        <span className="badge st-ZREALIZOWANY">{r.changed} {t('queueChanged')}</span>
        {(r.skipped_old ?? 0) > 0 &&
          <span className="badge st-ODPRAWA">{r.skipped_old} {t('queueSkippedOld')}</span>}
      </>}
    </div>
  )

  return (
    <Modal title={`${t(titleKey)} — ${companyCode}`} onClose={onClose} busy={busy} className="import-modal">
        <p style={{ color: 'var(--muted)', fontSize: 14, margin: '0 0 12px' }}>{t(hintKey)}</p>
        <FilePicker label={t('importFileLbl')} caption={t('importFileLbl')} accept=".xlsx,.xlsm"
                    disabled={busy} file={file} onChange={f => { setFile(f); setPreview(null); setResult(null) }} />
        {isQueueSync && (
          <label className="import-file">{t('queueDateFrom')}
            <input type="date" disabled={busy} value={dateFrom}
                   onChange={e => { setDateFrom(e.target.value); setPreview(null) }} />
          </label>
        )}
        {error && <p className="error">{error}</p>}
        {preview && !result && <Summary r={preview} />}
        {preview && !result && commitCount(preview) === 0 && (
          <p className="muted" role="status">
            {t('importNoChanges')}
            {(preview.skipped_old ?? 0) > 0 && dateFrom &&
              <> {t('queueSkippedOldHint').replace('{date}', formatDate(dateFrom))}</>}
          </p>
        )}
        {result && <p className="import-done"><CircleCheckIcon size={14} /> {t('importDone')} — <Summary r={result} /></p>}

        <div className="actions">
          <button className="btn secondary" disabled={busy} onClick={onClose}>
            {result ? t('ok') : t('cancel')}
          </button>
          {!result && !preview && (
            <button className="btn" disabled={!file || busy} onClick={() => run(true)}>
              {busy ? t('loading') : t('importPreviewBtn')}
            </button>
          )}
          {!result && preview && (
            <button className="btn" disabled={busy || commitCount(preview) === 0} onClick={() => run(false)}>
              {busy ? t('loading') : `${t('importCommitBtn')} (${commitCount(preview)})`}
            </button>
          )}
        </div>
    </Modal>
  )
}
