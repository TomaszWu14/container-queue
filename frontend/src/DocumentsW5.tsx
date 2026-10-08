import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AgencyMailPreviewModal } from './AgencyMailPreviewModal'
import { api, downloadFile, errorMessage } from './api'
import { Modal } from './components'
import { useT } from './i18n'
import { useUser } from './userContext'
import { formatDate } from './dates'
import type { AttachmentSuggestion, CompareReport, Container, InvoiceBatch, InvoiceJob } from './types'

/** W5 #31: panel propozycji podpięcia dokumentów z OCR na karcie kontenera.
 *  Akceptacja kopiuje wycinek PDF jako załącznik (z opcjonalnym typem dokumentu). */
export function AttachmentSuggestionsPanel({ container, onAccepted }: {
  container: Container
  onAccepted?: () => void
}) {
  const t = useT()
  const [suggestions, setSuggestions] = useState<AttachmentSuggestion[]>([])
  const [docTypes, setDocTypes] = useState<{ id: number; name: string }[]>([])
  const [typeBySuggestion, setTypeBySuggestion] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.get<AttachmentSuggestion[]>(`/api/containers/${container.id}/attachment-suggestions`)
      .then(rows => setSuggestions(Array.isArray(rows) ? rows : []))
      .catch(() => {})
  }, [container.id])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    api.get<typeof docTypes>('/api/customs/document-types?active_only=true')
      .then(setDocTypes).catch(() => {})
  }, [])

  const decide = async (s: AttachmentSuggestion, action: 'accept' | 'reject') => {
    setBusy(true)
    setError('')
    try {
      const body = action === 'accept'
        ? { document_type_id: typeBySuggestion[s.id] ? Number(typeBySuggestion[s.id]) : null }
        : {}
      await api.post(`/api/attachment-suggestions/${s.id}/${action}`, body)
      load()
      if (action === 'accept') onAccepted?.()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const proposed = suggestions.filter(s => s.status === 'proposed')
  if (proposed.length === 0) return null
  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>
          {t('docSuggestions')} <span className="count-chip">{proposed.length}</span>
        </h3>
      </div>
      <p className="muted" style={{ fontSize: 13, margin: '6px 0 0' }}>
        {t('docSuggestionsHint')}
      </p>
      {error && <p className="error">{error}</p>}
      <table className="grid" style={{ marginTop: 8 }}>
        <thead>
          <tr><th>{t('name')}</th><th>{t('invKindCol')}</th><th>{t('docType')}</th><th></th></tr>
        </thead>
        <tbody>
          {proposed.map(s => (
            <tr key={s.id}>
              <td>
                {s.filename}
                {s.page_to != null && s.page_from != null && s.page_to > s.page_from
                  && ` (${s.page_from}–${s.page_to})`}
                {s.invoice_number && <span className="muted"> · {s.invoice_number}</span>}
              </td>
              <td>{t(`invKind_${s.doc_kind}`)}</td>
              <td>
                <select aria-label={t('docType')} value={typeBySuggestion[s.id] ?? ''} disabled={busy}
                        onChange={e => setTypeBySuggestion(m =>
                          ({ ...m, [s.id]: e.target.value }))}>
                  <option value="">—</option>
                  {docTypes.map(dt => <option key={dt.id} value={dt.id}>{dt.name}</option>)}
                </select>
              </td>
              <td>
                <div className="row" style={{ gap: 6 }}>
                  <button className="btn small" disabled={busy}
                          onClick={() => decide(s, 'accept')}>{t('sgAccept')}</button>
                  <button className="btn small secondary" disabled={busy}
                          onClick={() => decide(s, 'reject')}>{t('sgReject')}</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** W5 #33/#34: raport rozjazdów dokument (OCR) ↔ system — tylko podgląd,
 *  nic nie nadpisuje danych. */
export function CompareModal({ job, onClose }: { job: InvoiceJob; onClose: () => void }) {
  const t = useT()
  const [report, setReport] = useState<CompareReport | null>(null)
  const [error, setError] = useState('')
  const packing = job.doc_kind === 'packing_list'

  useEffect(() => {
    const path = packing
      ? `/api/invoice-jobs/${job.id}/packing-compare`
      : `/api/invoice-jobs/${job.id}/order-compare`
    api.get<CompareReport>(path).then(setReport).catch(err => setError(errorMessage(err)))
  }, [job.id, packing])

  return (
    <Modal title={`${t('cmpTitle')}: ${job.filename}`} onClose={onClose}>
      {error && <p className="error">{error}</p>}
      {!report && !error && <p className="muted">…</p>}
      {report && (
        <>
          {report.kind === 'invoice' && (
            <p style={{ margin: '0 0 8px' }}>
              {t('cmpInvoiceTotal')}: <b>{report.invoice_total ?? '—'}</b>
              {' · '}{t('cmpPoTotal')}: <b>{report.po_total ?? '—'}</b>
              {report.diff_pct != null && (
                <> {' · '}{t('cmpDiff')}: <b>{report.diff_pct}%</b></>
              )}
              {report.exceeded && (
                <span className="badge st-OPOZNIONY" style={{ marginLeft: 8 }}>
                  {t('cmpExceeded')}
                </span>
              )}
            </p>
          )}
          {report.rows.length === 0 && <p className="muted">{t('cmpNoRows')}</p>}
          {report.rows.length > 0 && (
            <div style={{ overflowX: 'auto', maxHeight: '55vh', overflowY: 'auto' }}>
              <table className="grid">
                <thead>
                  <tr><th>REF</th><th>{t('cmpDocQty')}</th><th>{t('cmpSysQty')}</th>
                      <th>{t('status')}</th></tr>
                </thead>
                <tbody>
                  {report.rows.map((row, i) => (
                    <tr key={i}>
                      <td className="mono">{row.ref}</td>
                      <td>{row.doc_qty ?? '—'}</td>
                      <td>{row.sys_qty ?? '—'}</td>
                      <td>
                        <span className={`badge ${row.status === 'ok' ? 'st-DOSTARCZONY'
                          : row.status === 'qty_unknown' ? 'st-ZREALIZOWANY' : 'st-OPOZNIONY'}`}>
                          {t(`cmp_${row.status}`)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>{t('cmpReadOnly')}</p>
        </>
      )}
    </Modal>
  )
}

// role z dostępem do /api/customs/docs-gaps (spedytor: tylko swoje kontenery — audyt UI S10)
const DOCS_GAPS_ROLES = ['admin', 'logistics']   // bez spedytora: odprawa = agencja (2026-09-28)

/** W5 #32: sekcja „Braki dokumentów” na pulpicie (ETA ≤ horyzont, brakujące typy). */
export function DocsGapsCard() {
  const t = useT()
  const allowed = DOCS_GAPS_ROLES.includes(useUser()?.role ?? '')
  const [rows, setRows] = useState<{ id: number; container_no: string; eta: string | null
    missing: string[] }[]>([])
  useEffect(() => {
    if (!allowed) return
    api.get<typeof rows>('/api/customs/docs-gaps')
      .then(data => setRows(Array.isArray(data) ? data : [])).catch(() => {})
  }, [allowed])
  if (rows.length === 0) return null
  return (
    <section className="panel dash-card">
      <div className="dash-card-head">
        <span className="dash-card-title">{t('docsGapsTitle')}</span>
        <span className="count-chip">{rows.length}</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="grid">
          <thead>
            <tr><th>{t('containerNo')}</th><th>ETA</th><th>{t('missingDocs')}</th></tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.id}>
                <td><Link to={`/kontenery/${row.id}`} className="mono">{row.container_no}</Link></td>
                <td>{row.eta ? formatDate(row.eta) : '—'}</td>
                <td>{row.missing.join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

/** W5 #35: ZIP dokumentów miesiąca per spółka (archiwum kolejki). */
export function MonthlyZipBar({ companyCode }: { companyCode: string }) {
  const t = useT()
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const download = async () => {
    setBusy(true)
    setError('')
    try {
      await downloadFile(
        `/api/archive/attachments-zip?company_code=${encodeURIComponent(companyCode)}&month=${month}`,
        `dokumenty_${companyCode}_${month}.zip`)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="panel">
      <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <b>{t('monthlyZipTitle')}</b>
        <input aria-label={t('fieldMonth')} type="month" value={month} onChange={e => setMonth(e.target.value)} />
        <button className="btn small" disabled={busy || !month} onClick={download}>
          {busy ? '…' : t('monthlyZipBtn')}
        </button>
        <span className="muted" style={{ fontSize: 13 }}>{t('monthlyZipHint')}</span>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  )
}

/** W5 #36: podgląd wiadomości do agencji przed wysyłką dokumentów. */
export function SendDocsPreviewModal({ containerId, containerNo = '', onConfirm, onClose, busy }: {
  containerId: number
  containerNo?: string
  onConfirm: (force: boolean) => void   // force = świadome „wyślij mimo braków” z TEGO podglądu
  onClose: () => void
  busy: boolean
}) {
  const t = useT()
  const [preview, setPreview] = useState<{ subject: string; body: string
    missing: string[]; attachments: number; agency?: string | null; recipients?: string[]
    files?: { name: string; type: string | null }[] } | null>(null)
  const [error, setError] = useState('')
  // agencja bez kont: powiadomienie nie dotrze — droga mailowa z najnowszej paczki z aktualnym Excelem
  const [mailBatch, setMailBatch] = useState<InvoiceBatch | null | undefined>(undefined)
  const [mailOpen, setMailOpen] = useState(false)
  const noRecipients = preview?.recipients?.length === 0
  useEffect(() => {
    api.get<typeof preview>(`/api/customs/containers/${containerId}/send-docs/preview`)
      .then(setPreview).catch(err => setError(errorMessage(err)))
  }, [containerId])
  useEffect(() => {
    if (!noRecipients) return
    api.get<InvoiceBatch[]>(`/api/containers/${containerId}/invoice-batches`)
      .then(r => setMailBatch((Array.isArray(r) ? r : []).filter(b => b.attachment_id && b.excel_current)
        .sort((a, b) => b.id - a.id)[0] ?? null))
      .catch(() => setMailBatch(null))
  }, [containerId, noRecipients])
  if (mailOpen && mailBatch) return <AgencyMailPreviewModal batch={mailBatch} containerNo={containerNo} onClose={onClose} />
  return (
    <Modal title={t('sendDocsPreviewTitle')} onClose={onClose}>
      {error && <p className="error">{error}</p>}
      {!preview && !error && <p className="muted">…</p>}
      {preview && (
        <>
          {/* audyt 2026-10-06 #10/#18: to powiadomienie w aplikacji, nie e-mail — kto je dostanie */}
          <p className="muted" style={{ margin: '0 0 6px', fontSize: 13 }}>{t('sendDocsInAppHint')}</p>
          <p style={{ margin: '0 0 4px' }}>
            <b>{t('sendDocsRecipients')}:</b>{' '}
            {preview.recipients && preview.recipients.length > 0
              ? `${preview.agency ?? ''} — ${preview.recipients.join(', ')}`
              : <span className="error">{t('sendDocsNoRecipients')}</span>}
          </p>
          {noRecipients && mailBatch === null && <p className="error">{t('sendDocsNeedExcel')}</p>}
          <p style={{ margin: '0 0 4px' }}><b>{t('tplSubject')}:</b> {preview.subject}</p>
          <p style={{ whiteSpace: 'pre-wrap', background: 'var(--panel2, transparent)',
                      padding: 8, borderRadius: 6, margin: '0 0 8px' }}>{preview.body}</p>
          {preview.files && preview.files.length > 0 && (
            <div style={{ margin: '0 0 8px', fontSize: 13 }}>
              <b>{t('sendDocsFiles')} ({preview.files.length}):</b>
              <ul style={{ margin: '4px 0 0 18px', padding: 0 }}>
                {preview.files.map((f, i) => <li key={`${f.name}-${i}`}>{f.name}{f.type && <span className="muted"> · {f.type}</span>}</li>)}
              </ul>
            </div>
          )}
          {preview.missing.length > 0 && (
            <p style={{ margin: '0 0 8px' }}>
              <span className="badge cs-ZLECONA">{t('missingDocs')}</span>{' '}
              <span className="muted">{preview.missing.join(', ')}</span>
            </p>
          )}
          <div className="actions">
            <button className="btn secondary" onClick={onClose}>{t('cancel')}</button>
            {noRecipients ? (
              <button className="btn" disabled={!mailBatch} onClick={() => setMailOpen(true)}
                      title={mailBatch === null ? t('sendDocsNeedExcel') : t('invAgencyMailHint')}>
                {t('invAgencyMail')}
              </button>
            ) : (
              <button className="btn" disabled={busy} onClick={() => onConfirm(preview.missing.length > 0)}>
                {preview.missing.length > 0 ? t('sendAnyway') : t('sendDocsToAgency')}
              </button>
            )}
          </div>
        </>
      )}
    </Modal>
  )
}
