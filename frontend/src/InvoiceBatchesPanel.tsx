import { useCallback, useEffect, useState } from 'react'
import { api, downloadFile, errorMessage } from './api'
import { AgencyMailPreviewModal } from './AgencyMailPreviewModal'
import { AgencySadSection } from './AgencySadSection'
import { InvoiceReviewModal } from './InvoiceReviewModal'
import { CompareModal } from './DocumentsW5'
import { useT } from './i18n'
import type { AttachmentSuggestion, Container, InvoiceBatch, InvoiceJob } from './types'
import { formatDateTime, parseServerTs } from './dates'
import { useConfirm } from './ConfirmDialog'

// ARCH-004: cięcie/OCR/ekstrakcja idą w tle (upload → 202, dokumenty „uploaded”) — dopóki
// coś czeka, lista odświeża się sama co kilka sekund
export const INGEST_POLL_MS = 5000

/** Faktury (CIPL) → Excel — pipeline lokalny (bez zewnętrznej usługi).
 *  PDF-y przychodzą z poczekalni (IntakePanel), serwer w tle tnie go na dokumenty i ekstrahuje pozycje; użytkownik
 *  weryfikuje każdą fakturę w modalu, a Excel generuje przyciskiem — plik ląduje w załącznikach. */
export function InvoiceBatchesPanel({ container, onChanged }: {
  container: Container
  onChanged?: () => void   // eksport / usunięcie paczki → kafelki CI/PI/PL (§4 pkt 29)
}) {
  const t = useT()
  const { confirm } = useConfirm()
  const [mailBatch, setMailBatch] = useState<InvoiceBatch | null>(null)
  const [batches, setBatches] = useState<InvoiceBatch[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [reviewJob, setReviewJob] = useState<InvoiceJob | null>(null)
  const [compareJob, setCompareJob] = useState<InvoiceJob | null>(null)
  // W5 #31: licznik oczekujących propozycji podpięcia w module faktur
  const [proposedCount, setProposedCount] = useState(0)

  // nie ufamy kształtowi odpowiedzi — nie-tablica nie może wywalić karty kontenera
  const accept = (data: InvoiceBatch[]) => setBatches(Array.isArray(data) ? data : [])
  const fail = (err: unknown) => setError(errorMessage(err))

  const load = useCallback(() => {
    setBusy(true)
    api.get<InvoiceBatch[]>(`/api/containers/${container.id}/invoice-batches`)
      .then(accept).catch(fail).finally(() => setBusy(false))
    api.get<AttachmentSuggestion[]>(`/api/containers/${container.id}/attachment-suggestions`)
      .then(rows => setProposedCount(Array.isArray(rows)
        ? rows.filter(s => s.status === 'proposed').length : 0))
      .catch(() => {})
  }, [container.id])

  useEffect(() => { load() }, [load])

  const processing = batches.some(b => (b.jobs ?? []).some(j => j.status === 'uploaded'))
  useEffect(() => {
    if (!processing) return
    const timer = window.setTimeout(load, INGEST_POLL_MS)
    return () => window.clearTimeout(timer)
  }, [processing, batches, load])

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await fn()
      load()
      onChanged?.()
    } catch (err) {
      fail(err)
      setBusy(false)
    }
  }

  const exportBatch = async (batch: InvoiceBatch) => {
    if (!batch.ready && !(await confirm(t('invConfirmPartial')))) return
    run(() => api.post(`/api/invoice-batches/${batch.id}/export?partial=${!batch.ready}`, {}))
  }

  const removeBatch = async (batch: InvoiceBatch) => {
    if (!(await confirm(t('invConfirmDeleteBatch'), { danger: true }))) return
    run(() => api.del(`/api/invoice-batches/${batch.id}`))
  }

  const download = async (batch: InvoiceBatch) => {
    try {
      await downloadFile(`/api/attachments/${batch.attachment_id}/download`,
        batch.attachment_filename ?? `faktury_${batch.id}.xlsx`)
    } catch (err) {
      fail(err)
    }
  }

  // podgląd przed szkicem .eml — odbiorcy, załączniki, ostrzeżenia (AgencyMailPreviewModal)
  const agencyMail = (batch: InvoiceBatch) => { setError(''); setMailBatch(batch) }

  const statusClass =(job: InvoiceJob) => {
    if (job.status === 'confirmed') return 'st-DOSTARCZONY'
    if (job.status === 'error') return 'st-OPOZNIONY'
    if (job.status === 'extracted') return 'st-W_TRANSPORCIE'
    return 'st-ZREALIZOWANY'
  }
  const isInvoice = (job: InvoiceJob) => job.doc_kind === 'invoice' || job.doc_kind === 'proforma'
  // niepocięty zestaw w kolejce tła: „w kolejce” / „przetwarzanie od N min” zamiast „0 pozycji”
  const queueState = (job: InvoiceJob) => {
    if (!job.processing_started_at) return t('invQueued')
    const min = Math.max(0, Math.round((Date.now() - parseServerTs(job.processing_started_at).getTime()) / 60000))
    return (min >= 30 ? t('invProcessingStale') : t('invProcessingSince')).replace('{n}', String(min))
  }

  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>
          {t('invoicesCipl')}
          {proposedCount > 0 && (
            <span className="badge st-W_TRANSPORCIE" style={{ marginLeft: 8 }}
                  title={t('docSuggestionsHint')}>
              {t('docSuggestions')}: {proposedCount}
            </span>
          )}
        </h3>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn small secondary" disabled={busy} onClick={load}>
            {t('refreshStatus')}
          </button>
        </div>
      </div>
      <p className="muted" style={{ fontSize: 13, margin: '6px 0 0' }}>{t('invoicesHint')}</p>
      {processing && <p className="muted" role="status" style={{ fontSize: 13 }}>{t('invProcessingInBackground')}</p>}
      {error && <p className="error">{error}</p>}
      {batches.length === 0 && <p style={{ color: 'var(--muted)' }}>{t('noInvoiceBatches')}</p>}
      {batches.map(batch => (
        <div key={batch.id} style={{ marginTop: 12, paddingTop: 8, borderTop: '1px solid var(--border)' }}>
          <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <span className={`badge ${batch.ready ? 'st-DOSTARCZONY' : 'st-W_TRANSPORCIE'}`}>
              {batch.ready ? t('invoicesReady') : `${batch.confirmed}/${batch.total} ${t('invConfirmed')}`}
            </span>
            <span style={{ color: 'var(--muted)', fontSize: 13 }}>
              {formatDateTime(batch.created_at)}
              {batch.supplier_name && ` · ${batch.supplier_name}`}
            </span>
            {batch.confirmed > 0 && (
              <button className="btn small" disabled={busy} onClick={() => exportBatch(batch)}>
                {batch.ready ? t('invGenerateExcel') : t('invGeneratePartial')}
              </button>
            )}
            {batch.attachment_id && (
              <button className="btn small secondary" onClick={() => download(batch)}
                      title={batch.excel_current ? undefined : t('invExcelStale')}>
                {t('downloadExcel')}{!batch.excel_current && ` (${t('invExcelStaleShort')})`}
              </button>
            )}
            {batch.attachment_id && (
              // szkic .eml — Outlook otwiera go jako nową wiadomość, użytkownik sam wysyła
              <button className="btn small secondary" disabled={busy || !batch.excel_current}
                      title={batch.excel_current ? t('invAgencyMailHint') : t('invExcelStale')}
                      onClick={() => agencyMail(batch)}>
                {t('invAgencyMail')}
              </button>
            )}
            {batch.attachment_id && (
              // XML SADUE do importu w WinSAD agencji (te same pozycje co Excel; 409 = co poprawić)
              <button className="btn small secondary" disabled={busy} title={t('invSadueXmlHint')}
                      onClick={() => downloadFile(`/api/invoice-batches/${batch.id}/sadue.xml`,
                                                  `SAD_${container.container_no}.xml`).catch(fail)}>
                {t('invSadueXml')}
              </button>
            )}
            <button className="btn small danger" disabled={busy} onClick={() => removeBatch(batch)}>
              {t('invDeleteBatch')}
            </button>
          </div>
          <ul style={{ margin: '6px 0 0 18px', fontSize: 14, lineHeight: 1.9 }}>
            {batch.jobs.map(job => (
              <li key={job.id}>
                <span className={`badge ${statusClass(job)}`}>{t(`invStatus_${job.status}`)}</span>{' '}
                {job.filename}
                {job.page_to > job.page_from && ` (${job.page_from}–${job.page_to})`}
                {' '}<span className="muted">· {t(`invKind_${job.doc_kind}`)}</span>
                {job.ocr_used && <span className="badge st-ODPRAWA" style={{ marginLeft: 6 }} title={t('invOcrHint')}>{t('invOcr')}</span>}
                {job.invoice_number && ` · ${job.invoice_number}`}
                {job.status === 'uploaded' && <span className="muted"> · {queueState(job)}</span>}
                {isInvoice(job) && job.status !== 'error' && job.status !== 'ignored' && job.status !== 'uploaded' && (
                  <span className="muted"> · {job.items_count} {t('refRows')}</span>
                )}
                {isInvoice(job) && (job.status === 'extracted' || job.status === 'confirmed') && (
                  <button className="btn small secondary" style={{ marginLeft: 8 }}
                          onClick={() => setReviewJob(job)}>
                    {t('invReview')}
                  </button>
                )}
                {/* W5 #33/#34: raport rozjazdów dokument ↔ system (tylko podgląd) */}
                {((isInvoice(job) && (job.status === 'extracted' || job.status === 'confirmed'))
                  || (job.doc_kind === 'packing_list' && job.status === 'packing_list')) && (
                  <button className="btn small secondary" style={{ marginLeft: 8 }}
                          onClick={() => setCompareJob(job)}>
                    {t('cmpBtn')}
                  </button>
                )}
                {(isInvoice(job) || job.doc_kind === 'packing_list') && (job.status === 'error' || job.status === 'ignored') && (
                  <button className="btn small secondary" style={{ marginLeft: 8 }} disabled={busy}
                          onClick={() => run(() => api.post(`/api/invoice-jobs/${job.id}/reprocess`, {}))}>
                    {t(job.status === 'ignored' ? 'invRestore' : 'invReprocess')}
                  </button>
                )}
                {(isInvoice(job) || job.doc_kind === 'packing_list') && !['confirmed', 'ignored', 'uploaded'].includes(job.status) && (
                  <button className="btn small secondary" style={{ marginLeft: 8 }} disabled={busy}
                          title={t('invIgnoreConfirm')}
                          onClick={async () => (await confirm(t('invIgnoreConfirm')))
                            && run(() => api.post(`/api/invoice-jobs/${job.id}/ignore`, {}))}>
                    {t('invIgnore')}
                  </button>
                )}
                {job.error && <span className="error"> {job.error}</span>}
              </li>
            ))}
          </ul>
          {/* po wysłaniu faktur (jest Excel) — odpowiedź agencji: potwierdzenie i draft SAD */}
          {batch.attachment_id && <AgencySadSection batchId={batch.id} />}
        </div>
      ))}
      {mailBatch && <AgencyMailPreviewModal batch={mailBatch} containerNo={container.container_no}
                                            onClose={() => setMailBatch(null)} />}
      {compareJob && <CompareModal job={compareJob} onClose={() => setCompareJob(null)} />}
      {reviewJob && (
        <InvoiceReviewModal jobId={reviewJob.id} onClose={() => setReviewJob(null)}
                            onSaved={load} />
      )}
    </div>
  )
}
