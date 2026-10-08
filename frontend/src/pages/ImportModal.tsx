import { CircleCheckIcon } from 'lucide-react'
import { useState } from 'react'
import { api, errorMessage } from '../api'
import { Modal } from '../components'
import { formatDate } from '../dates'
import { useT } from '../i18n'
import { ImportErrors, type ImportRowError } from './ImportErrors'
import { FilePicker } from '../FilePicker'

interface ImportRow {
  container_no: string
  status: 'new' | 'exists' | 'invalid' | 'duplicate'
  note: string
  supplier: string
  eta: string
  notify_date: string
  warehouse: string
  forwarder: string
  transport: string
}

// podgląd importu REF (zamówienia): backend zwraca je w tym samym polu `rows`
interface RefRow {
  order_number: string
  material: string
  description: string
  quantity: string | number
  unit: string
}

interface ImportResult {
  dry_run: boolean
  counts: { total?: number; new?: number; exists?: number; invalid?: number;
            duplicate?: number; rows?: number; orders?: number; orders_linked?: number }
  rows?: ImportRow[] | RefRow[]
  errors?: ImportRowError[]
  imported?: number
  failed?: number
  invalid_numbers?: string[]
}

const STATUS_BADGE: Record<ImportRow['status'], string> = {
  new: 'st-DOSTARCZONY', exists: 'st-ZREALIZOWANY',
  invalid: 'cs-REWIZJA', duplicate: 'st-ODPRAWA',
}

export default function ImportModal({ companyCode, onDone, onClose,
  endpoint = '/api/import/containers', titleKey = 'importExcel' }: {
  companyCode: string
  onDone: () => void
  onClose: () => void
  endpoint?: string
  titleKey?: string
}) {
  const t = useT()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportResult | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const run = async (dryRun: boolean) => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      // wspólny klient: obsługa 401→refresh i błędów (koniec cichej porażki uploadu)
      const body = await api.upload<ImportResult>(
        `${endpoint}?company_code=${encodeURIComponent(companyCode)}&dry_run=${dryRun}`, file)
      if (dryRun) setPreview(body)
      else {
        setResult(body)
        onDone()
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const statusLabel = (s: ImportRow['status']) => ({
    new: t('importNew'), exists: t('importExists'),
    invalid: t('importInvalid'), duplicate: t('importDuplicate'),
  })[s]

  return (
    <Modal title={`${t(titleKey)} — ${companyCode}`} onClose={onClose} busy={busy} className="import-modal">
        <FilePicker label={t('importFileLbl')} caption={t('importFileLbl')} accept=".xlsx,.xlsm"
                    disabled={busy} file={file} onChange={f => { setFile(f); setPreview(null); setResult(null) }} />
        {error && <p className="error">{error}</p>}

        {preview && !result && preview.counts.orders !== undefined && (
          <>
            <div className="import-counts">
              <span className="badge st-DOSTARCZONY">{preview.counts.rows} {t('refRows')}</span>
              <span className="badge st-W_TRANSPORCIE">{preview.counts.orders} {t('orders')}</span>
              <span className="badge st-ZREALIZOWANY">{preview.counts.orders_linked} {t('refLinked')}</span>
            </div>
            <ImportErrors errors={preview.errors} />
            <div className="import-rows">
              <div style={{ overflowX: 'auto' }}>
                <table className="grid" style={{ minWidth: 720 }}>
                  <thead>
                    <tr><th>{t('order')}</th><th>REF</th><th>{t('refDesc')}</th><th>{t('refQty')}</th></tr>
                  </thead>
                  <tbody>
                    {((preview.rows ?? []) as RefRow[]).map((row, index) => (
                      <tr key={`${row.order_number}|${row.material}|${index}`}>
                        <td className="mono">{row.order_number}</td>
                        <td className="mono">{row.material}</td>
                        <td>{row.description}</td>
                        <td>{row.quantity} {row.unit}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
        {preview && !result && preview.counts.orders === undefined && (
          <>
            <div className="import-counts">
              <span className="badge st-DOSTARCZONY">{preview.counts.new} {t('importNew')}</span>
              <span className="badge st-ZREALIZOWANY">{preview.counts.exists} {t('importExists')}</span>
              {(preview.counts.duplicate ?? 0) > 0 && (
                <span className="badge st-ODPRAWA">{preview.counts.duplicate} {t('importDuplicate')}</span>
              )}
              {(preview.counts.invalid ?? 0) > 0 && (
                <span className="badge cs-REWIZJA">{preview.counts.invalid} {t('importInvalid')}</span>
              )}
            </div>
            {(preview.invalid_numbers?.length ?? 0) > 0 && (
              <details className="import-invalid">
                <summary>{t('importInvalidList')} ({preview.invalid_numbers!.length})</summary>
                <div className="import-invalid-nums mono">{preview.invalid_numbers!.join(', ')}</div>
              </details>
            )}
            <div className="import-rows">
              <div style={{ overflowX: 'auto' }}>
                <table className="grid" style={{ minWidth: 720 }}>
                  <thead>
                    <tr>
                      <th>{t('containerNo')}</th><th>{t('status')}</th>
                      <th>{t('supplier')}</th><th>{t('eta')}</th>
                      <th>{t('notifyDate')}</th><th>{t('warehouse')}</th>
                      <th>{t('forwarder')}</th><th>{t('transport')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {((preview.rows ?? []) as ImportRow[]).map((row, index) => (
                      <tr key={`${row.container_no}|${index}`}>
                        <td className="mono">{row.container_no}</td>
                        <td>
                          <span className={`badge ${STATUS_BADGE[row.status]}`} title={row.note}>
                            {statusLabel(row.status)}
                          </span>
                        </td>
                        <td>{row.supplier}</td>
                        <td>{formatDate(row.eta)}</td>
                        <td>{formatDate(row.notify_date)}</td>
                        <td>{row.warehouse}</td>
                        <td>{row.forwarder}</td>
                        <td>{row.transport}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {result && result.counts.orders !== undefined && (
          <p className="import-done">
            <CircleCheckIcon size={14} /> {t('importDone')}: <b>{result.imported}</b> {t('refRows')} ({result.counts.orders} {t('orders')})
          </p>
        )}
        {result && result.counts.orders === undefined && (
          <p className="import-done">
            <CircleCheckIcon size={14} /> {t('importDone')}: <b>{result.imported}</b> / {result.counts.total}
            {' '}({result.counts.exists} {t('importExists')}
            {(result.counts.invalid ?? 0) > 0 && <>, {result.counts.invalid} {t('importInvalid')}</>}
            {(result.failed ?? 0) > 0 && <>, <span className="error">{result.failed} {t('importFailed')}</span></>})
          </p>
        )}

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
            <button className="btn"
                    disabled={busy || (preview.counts.orders !== undefined
                      ? preview.counts.rows === 0 : preview.counts.new === 0)}
                    onClick={() => run(false)}>
              {busy ? t('loading') : `${t('importCommitBtn')} (${preview.counts.orders !== undefined ? preview.counts.rows : preview.counts.new})`}
            </button>
          )}
        </div>
    </Modal>
  )
}
