// Podgląd maila do agencji PRZED pobraniem szkicu .eml (2026-10-06: „nie widzę, co wyszło i czy
// jest OK”): odbiorcy, temat, każdy załącznik do otwarcia, ostrzeżenia, treść. Dane = te same
// części, z których serwer składa .eml (GET …/agency-mail/preview).
import { CircleCheckIcon, TriangleAlertIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, downloadFile, errorMessage } from './api'
import { useT } from './i18n'
import { Modal } from './Modal'
import type { InvoiceBatch } from './types'

interface PreviewFile {
  name: string; size: number; kind: 'excel' | 'symbols' | 'sadue' | 'invoice' | 'packing_list' | 'bl'
  job_id: number | null; attachment_id?: number | null
}
export interface MailPreview {
  to: string[]; cc: string[]; subject: string; body: string; agency: string
  warnings: string[]; attachments: PreviewFile[]
}

const kb = (b: number) => (b >= 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} kB`)

export function AgencyMailPreviewModal({ batch, containerNo, onClose }: {
  batch: InvoiceBatch
  containerNo: string
  onClose: () => void
}) {
  const t = useT()
  const [preview, setPreview] = useState<MailPreview | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get<MailPreview>(`/api/invoice-batches/${batch.id}/agency-mail/preview`)
      .then(p => { if (p && Array.isArray(p.attachments)) setPreview(p) })
      .catch(e => setError(errorMessage(e)))
  }, [batch.id])

  const open = (file: PreviewFile) => {
    const url = file.kind === 'excel' ? `/api/attachments/${batch.attachment_id}/download`
      : file.kind === 'symbols' ? `/api/invoice-batches/${batch.id}/symbols.xlsx`
      : file.kind === 'sadue' ? `/api/invoice-batches/${batch.id}/sadue.xml`
        : file.attachment_id ? `/api/attachments/${file.attachment_id}/download`
          : `/api/invoice-jobs/${file.job_id}/pdf`
    downloadFile(url, file.name).catch(e => setError(errorMessage(e)))
  }
  const eml = async () => {
    setBusy(true); setError('')
    try {
      await downloadFile(`/api/invoice-batches/${batch.id}/agency-mail.eml`, `faktury_${containerNo}.eml`)
      onClose()
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  return (
    <Modal title={t('mailPrevTitle')} onClose={onClose} busy={busy} width={720} className="mail-prev">
      {error && <p className="error">{error}</p>}
      {!preview && !error && <p className="muted">…</p>}
      {preview && <>
        <dl className="mail-prev-head">
          <dt>{t('mailPrevAgency')}</dt><dd>{preview.agency}</dd>
          <dt>{t('mailPrevTo')}</dt><dd>{preview.to.join(', ')}</dd>
          {preview.cc.length > 0 && <><dt>{t('mailPrevCc')}</dt><dd>{preview.cc.join(', ')}</dd></>}
          <dt>{t('mailPrevSubject')}</dt><dd>{preview.subject}</dd>
        </dl>
        {preview.warnings.length > 0
          ? <div className="mail-prev-warn" role="alert">
              <b><TriangleAlertIcon size={14} aria-hidden="true" /> {t('mailPrevWarnings')}</b>
              <ul>{preview.warnings.map(w => <li key={w}>{w}</li>)}</ul>
            </div>
          : <p className="mail-prev-ok"><CircleCheckIcon size={14} aria-hidden="true" /> {t('mailPrevAllOk')}</p>}
        <h4 className="mail-prev-h">{t('mailPrevFiles')} ({preview.attachments.length})</h4>
        <table className="grid">
          <tbody>
            {preview.attachments.map(f => (
              <tr key={`${f.kind}-${f.job_id ?? f.name}`}>
                <td>{f.name}</td>
                <td className="muted">{t(`mailPrevKind_${f.kind}`)}</td>
                <td className="muted mono">{kb(f.size)}</td>
                <td><button type="button" className="btn small secondary" onClick={() => open(f)}>{t('mailPrevOpen')}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <details className="mail-prev-body">
          <summary>{t('mailPrevBody')}</summary>
          <pre>{preview.body}</pre>
        </details>
        <p className="muted" style={{ fontSize: 13 }}>{t('invAgencyMailHint')}</p>
      </>}
      <div className="actions">
        <button type="button" className="btn secondary" disabled={busy} onClick={onClose}>{t('cancel')}</button>
        <button type="button" className="btn" data-autofocus disabled={busy || !preview} onClick={eml}>
          {busy ? t('loading') : t('mailPrevDownload')}
        </button>
      </div>
    </Modal>
  )
}
