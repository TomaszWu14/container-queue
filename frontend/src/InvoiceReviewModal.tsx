import { useEffect, useState } from 'react'
import { api, downloadFile, errorMessage } from './api'
import { Modal } from './components'
import { useT } from './i18n'
import { type Conformity, InvoiceConformityNote, isConformity } from './InvoiceConformityNote'
import type { InvoiceItem, InvoiceJobDetail } from './types'

type Draft = Pick<InvoiceItem, 'id' | 'master_ref' | 'qty' | 'amount' | 'weight_net'
  | 'weight_gross' | 'skipped'>

const toDraft = (item: InvoiceItem): Draft => ({
  id: item.id, master_ref: item.master_ref, qty: item.qty, amount: item.amount,
  weight_net: item.weight_net, weight_gross: item.weight_gross, skipped: item.skipped,
})

/** Weryfikacja pozycji jednej faktury: REF master (rozstrzyga X/X1), ilość, kwota, wagi,
 *  pominięcie. „Zatwierdź” blokuje przy pozycjach niejednoznacznych (backend 409). */
export function InvoiceReviewModal({ jobId, onClose, onSaved }: {
  jobId: number
  onClose: () => void
  onSaved: () => void
}) {
  const t = useT()
  const [job, setJob] = useState<InvoiceJobDetail | null>(null)
  const [drafts, setDrafts] = useState<Record<number, Draft>>({})
  const [invoiceNo, setInvoiceNo] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [conformity, setConformity] = useState<Conformity | null>(null)
  const [reason, setReason] = useState('')

  const accept = (data: InvoiceJobDetail) => {
    setJob(data)
    setInvoiceNo(data.invoice_number)
    setDrafts(Object.fromEntries((data.items ?? []).map(item => [item.id, toDraft(item)])))
  }

  useEffect(() => {
    api.get<InvoiceJobDetail>(`/api/invoice-jobs/${jobId}`).then(accept)
      .catch(err => setError(errorMessage(err)))
    loadConformity()
  }, [jobId])   // eslint-disable-line react-hooks/exhaustive-deps

  // zgodność z kontenerem paczki (spec 2026-10-01): sprzeczna blokuje, niepewna wymaga powodu
  const loadConformity = () =>
    api.get<Conformity>(`/api/invoice-jobs/${jobId}/conformity`)
      .then(data => setConformity(isConformity(data) ? data : null)).catch(() => setConformity(null))

  const linkOrders = async () => {
    try {
      await api.post<string[]>(`/api/invoice-jobs/${jobId}/link-orders`, {})
      await loadConformity()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  // „wrzuć do X”: dokument znika z tej paczki — odświeżamy listę i zamykamy okno
  const moveTo = async (containerId: number) => {
    try {
      await api.post(`/api/invoice-jobs/${jobId}/move`, { container_id: containerId })
      onSaved()
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  // faktura na kilka kontenerów: kopia z pozycjami w paczce drugiego kontenera (PR 3)
  const copyTo = async (containerId: number) => {
    try {
      await api.post(`/api/invoice-jobs/${jobId}/copy`, { container_id: containerId })
      await loadConformity()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const edit = (id: number, changes: Partial<Draft>) =>
    setDrafts(d => ({ ...d, [id]: { ...d[id], ...changes } }))

  const save = async (confirm: boolean) => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const data = await api.put<InvoiceJobDetail>(`/api/invoice-jobs/${jobId}/review`, {
        items: Object.values(drafts), invoice_number: invoiceNo, confirm,
        ...(confirm && reason.trim() ? { conformity_reason: reason.trim() } : {}),
      })
      accept(data)
      onSaved()
      if (confirm) onClose()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const matchClass = (status: InvoiceItem['match_status']) =>
    status === 'matched' ? 'st-DOSTARCZONY' : status === 'ambiguous' ? 'st-OPOZNIONY' : 'st-ZREALIZOWANY'
  const matchLabel = (status: InvoiceItem['match_status']) =>
    status === 'matched' ? t('invMatched') : status === 'ambiguous' ? t('invAmbiguous') : t('invUnmatched')

  const blocked = conformity?.status === 'conflict'
    || (conformity?.status === 'uncertain' && !conformity.ack && !reason.trim())
  const ambiguous = (job?.items ?? []).some(i => i.match_status === 'ambiguous' && !drafts[i.id]?.skipped)
  // audyt 2026-10-06 #26: bez dopasowania NIE blokuje, ale w Excelu brak nazwy PL / CN, a pozycja
  // wypada z kartoteki symboli dla agencji — widoczne przed „Zatwierdź”
  const unmatched = (job?.items ?? []).filter(i => i.match_status === 'unmatched'
    && !drafts[i.id]?.skipped && !drafts[i.id]?.master_ref).length

  return (
    <Modal title={`${t('invReviewTitle')}${job ? ` — ${job.filename}` : ''}`} onClose={onClose}>
      <div className="invoice-review">
        {error && <p className="error">{error}</p>}
        {job && (
          <>
            <div className="row" style={{ gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 14 }}>
                {t('invInvoiceNo')}
                <input value={invoiceNo} onChange={e => setInvoiceNo(e.target.value)} style={{ width: 160 }} />
              </label>
              {job.container_no && <span className="muted">{t('containerNo')}: {job.container_no}</span>}
              {job.delivery_terms && <span className="muted">{job.delivery_terms}</span>}
              {job.status === 'confirmed' && <span className="badge st-DOSTARCZONY">{t('invConfirmed1')}</span>}
              {job.ocr_used && <span className="badge st-ODPRAWA" title={t('invOcrHint')}>{t('invOcr')}</span>}
              {/* audyt #25: oryginał obok tabeli pozycji — weryfikacja bez szukania pliku */}
              <button type="button" className="btn small secondary"
                      onClick={() => downloadFile(`/api/invoice-jobs/${jobId}/pdf`, job.filename)
                        .catch(err => setError(errorMessage(err)))}>{t('invOpenPdf')}</button>
            </div>
            {conformity && <InvoiceConformityNote conformity={conformity} reason={reason}
                                                  onReason={setReason} onLink={linkOrders}
                                                  onMove={moveTo} onCopy={copyTo} />}
            {ambiguous && <p className="muted" style={{ fontSize: 13 }}>{t('invAmbiguousHint')}</p>}
            {job.items.length === 0 && <p className="muted">{t('invNoItems')}</p>}
            {job.items.length > 0 && (
              <div style={{ overflowX: 'auto', marginTop: 8 }}>
                <table className="grid" style={{ minWidth: 980 }}>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>{t('invRawRef')}</th>
                      <th>{t('invMasterRef')}</th>
                      <th>{t('invNamePl')}</th>
                      <th>{t('invQty')}</th>
                      <th>{t('invAmount')}</th>
                      <th>{t('invNetWeight')}</th>
                      <th>{t('invGrossWeight')}</th>
                      <th>{t('invCn')}</th>
                      <th>{t('matSent')}</th>
                      <th>{t('invUomFactor')}</th>
                      <th>{t('invMatch')}</th>
                      <th>{t('invSkip')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {job.items.map(item => {
                      const d = drafts[item.id] ?? toDraft(item)
                      return (
                        <tr key={item.id} className={d.skipped ? 'muted' : ''}>
                          <td>{item.line_no}</td>
                          <td className="mono" title={item.descr}>{item.raw_ref}</td>
                          <td>
                            <input aria-label={t('invMasterRef')} value={d.master_ref} style={{ width: 120 }}
                                   className={item.match_status === 'ambiguous' ? 'invalid' : ''}
                                   onChange={e => edit(item.id, { master_ref: e.target.value })} />
                            {item.ml_suggestion && d.master_ref !== item.ml_suggestion && (
                              <div style={{ fontSize: 12, marginTop: 2 }}>
                                <span className="muted" title={t('invMlSuggest')}>
                                  ML: <span className="mono">{item.ml_suggestion}</span>
                                  {item.ml_confidence !== null && ` (${Math.round(item.ml_confidence * 100)}%)`}
                                </span>{' '}
                                <button type="button" className="btn small secondary"
                                        onClick={() => edit(item.id, { master_ref: item.ml_suggestion })}>
                                  {t('invMlApply')}
                                </button>
                              </div>
                            )}
                          </td>
                          <td>{item.name_pl || <span className="muted">—</span>}</td>
                          <td><input aria-label={t('invQty')} value={d.qty} style={{ width: 70 }}
                                     onChange={e => edit(item.id, { qty: e.target.value })} /></td>
                          <td><input aria-label={t('invAmount')} value={d.amount} style={{ width: 80 }}
                                     onChange={e => edit(item.id, { amount: e.target.value })} /></td>
                          <td><input value={d.weight_net} style={{ width: 70 }}
                                     title={item.weight_source === 'pl' ? t('invWeightFromPl') : undefined}
                                     onChange={e => edit(item.id, { weight_net: e.target.value })} /></td>
                          <td><input aria-label={t('invGrossWeight')} value={d.weight_gross} style={{ width: 70 }}
                                     onChange={e => edit(item.id, { weight_gross: e.target.value })} /></td>
                          <td>{item.tariff_cn || <span className="muted">—</span>}</td>
                          <td>{item.sent ? 'TAK' : 'NIE'}</td>
                          <td>{item.uom_factor || <span className="muted">—</span>}</td>
                          <td>
                            <span className={`badge ${matchClass(item.match_status)}`}>{matchLabel(item.match_status)}</span>
                            {item.match_status === 'matched' && item.match_source && (
                              <span className="muted" style={{ fontSize: 12 }}> · {t(`invMlSource_${item.match_source}`)}</span>
                            )}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            <input type="checkbox" checked={d.skipped} aria-label={t('invSkip')}
                                   onChange={e => edit(item.id, { skipped: e.target.checked })} />
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
        {unmatched > 0 && (
          <p className="inv-unmatched-note" role="status">{t('invUnmatchedWarn').replace('{n}', String(unmatched))}</p>
        )}
        <div className="actions">
          <button className="btn secondary" disabled={busy} onClick={onClose}>{t('cancel')}</button>
          <button className="btn secondary" disabled={busy || !job} onClick={() => save(false)}>{t('invSaveDraft')}</button>
          <button className="btn" disabled={busy || !job || !invoiceNo.trim() || blocked}
                  title={invoiceNo.trim() ? undefined : t('invConfirmNeedsNumber')}
                  onClick={() => save(true)}>{t('invConfirm')}</button>
        </div>
      </div>
    </Modal>
  )
}
