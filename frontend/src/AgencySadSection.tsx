// Sekcja „Agencja” pod paczką faktur (spec 2026-09-29-agencja-draft-sad, PR 1): potwierdzenie
// odbioru, wersje draftu SAD z maila agencji, decyzja „akceptuję / do poprawy” (najnowsza wersja).
// PR 2: „Porównaj” przy każdej wersji (SadCompareModal) + podsumowanie ostatniego porównania.
// XML z WinSAD przychodzi po PDF: „+ XML” dołącza go do wersji, dane porównania bierzemy wtedy z XML.
import { useCallback, useEffect, useState } from 'react'
import { FileButton } from './FilePicker'
import { api, downloadFile, errorMessage } from './api'
import { formatDateTime } from './dates'
import { useT } from './i18n'
import { SadCompareModal } from './SadCompareModal'
import type { AgencySadState, SadDraft } from './types'

interface UploadResult { draft: SadDraft; created: boolean; state: AgencySadState }

// nie ufamy kształtowi odpowiedzi (jak panel paczek) — zły kształt nie może wywalić karty kontenera
const valid = (s: AgencySadState | null | undefined): AgencySadState | null =>
  s && Array.isArray(s.drafts) ? s : null

// kolory decyzji jak podsumowanie porównania obok (st-OPOZNIONY nie miał reguły CSS — „do poprawy” był szary)
const DECISION_CLASS: Record<SadDraft['decision'], string> = {
  pending: '', accepted: 'badge-ok', rejected: 'badge-danger',
}

export function AgencySadSection({ batchId }: { batchId: number }) {
  const t = useT()
  const base = `/api/invoice-batches/${batchId}`
  const [state, setState] = useState<AgencySadState | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [comment, setComment] = useState('')
  const [comparing, setComparing] = useState<SadDraft | null>(null)

  const load = useCallback(() => {
    api.get<AgencySadState>(`${base}/sad-drafts`)
      .then(s => setState(valid(s))).catch(err => setError(errorMessage(err)))
  }, [base])
  useEffect(() => { load() }, [load])

  const act = async (fn: () => Promise<AgencySadState>) => {
    setBusy(true)
    setError('')
    setNote('')
    try {
      const next = valid(await fn())
      setState(prev => next ?? prev)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const upload = (file: File) => act(async () => {
    const res = await api.upload<UploadResult>(`${base}/sad-drafts`, file)
    setNote(res.created ? '' : t('sadDuplicate').replace('{v}', String(res.draft.version)))
    return res.state
  })
  const decide = (draft: SadDraft, decision: 'accepted' | 'rejected') => act(async () => {
    const next = await api.post<AgencySadState>(`${base}/sad-drafts/${draft.id}/decision`,
      { decision, comment: decision === 'rejected' ? comment.trim() : '' })
    setRejecting(false)
    setComment('')
    return next
  })
  const uploadXml = (draft: SadDraft, file: File) => act(async () =>
    (await api.upload<{ created: boolean; state: AgencySadState }>(
      `${base}/sad-drafts/${draft.id}/xml`, file)).state)
  const showFile = async (attachmentId: number, filename: string) => {
    setError('')
    try {
      await downloadFile(`/api/attachments/${attachmentId}/download`, filename)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  if (!state) return error ? <p className="error">{error}</p> : null
  const newest = state.drafts[0]
  return (
    <div className="agency-sad" style={{ marginTop: 8 }}>
      <b>{t('sadTitle')}</b>{' · '}
      {state.ack
        ? <span>✓ {t('sadAcked')} {formatDateTime(state.ack.at)} ({t(`sadSource_${state.ack.source}`)}{state.ack.by ? `, ${state.ack.by}` : ''})</span>
        : <span className="muted">{t('sadNotAcked')}</span>}
      <div className="row" style={{ gap: 8, marginTop: 6 }}>
        {!state.ack && (
          <button type="button" className="btn small secondary" disabled={busy}
                  onClick={() => act(() => api.post<AgencySadState>(`${base}/agency-ack`, {}))}>
            {t('sadAckBtn')}
          </button>
        )}
        <FileButton accept="application/pdf" disabled={busy}
                    onFiles={([f]) => { if (f) upload(f) }}>{t('sadUpload')}</FileButton>
      </div>
      {note && <p className="muted" role="status">{note}</p>}
      {error && <p className="error">{error}</p>}
      {state.drafts.length > 0 && (
        <ul style={{ margin: '6px 0 0 18px', fontSize: 14 }}>
          {state.drafts.map(d => (
            <li key={d.id}>
              v{d.version} · {formatDateTime(d.created_at)} · <span className={`badge ${DECISION_CLASS[d.decision] ?? ''}`}>{t(`sadDecision_${d.decision}`)}</span>
              {' '}<button type="button" className="btn small secondary"
                           onClick={() => showFile(d.attachment_id, d.filename)}>{t('sadShowPdf')}</button>
              {' '}{d.xml_attachment_id
                ? <button type="button" className="btn small secondary"
                          onClick={() => showFile(d.xml_attachment_id!, d.xml_filename ?? 'SAD.xml')}>{t('sadShowXml')}</button>
                : <FileButton accept=".xml,application/xml,text/xml" disabled={busy}
                              onFiles={([f]) => { if (f) uploadXml(d, f) }}>{t('sadAddXml')}</FileButton>}
              {d.data_from && <>{' '}<span className={`badge ${d.data_from === 'xml' ? 'badge-ok' : ''}`}>
                {t(`sadData_${d.data_from}`)}</span></>}
              {' '}<button type="button" className="btn small secondary" onClick={() => setComparing(d)}>
                {t('sadCompare')}</button>
              {d.summary && (
                <>{' '}<span className={`badge ${d.summary.all_ok ? 'badge-ok' : 'badge-danger'}`}>
                  {d.summary.all_ok
                    ? t('sadSummaryOk').replace('{ok}', String(d.summary.ok)).replace('{n}', String(d.summary.groups))
                    : t('sadSummaryIssues').replace('{n}', String(d.summary.diff + d.summary.manual))}
                </span></>
              )}
              {d.comment && <span className="muted"> · „{d.comment}”</span>}
              {d.decided_by && <span className="muted"> · {d.decided_by}</span>}
            </li>
          ))}
        </ul>
      )}
      {newest && newest.decision === 'pending' && !rejecting && (
        <div className="row" style={{ gap: 8, marginTop: 6 }}>
          <button type="button" className="btn small" disabled={busy}
                  onClick={() => decide(newest, 'accepted')}>{t('sadAccept')}</button>
          <button type="button" className="btn small secondary" disabled={busy}
                  onClick={() => setRejecting(true)}>{t('sadReject')}</button>
        </div>
      )}
      {newest && rejecting && (
        <div className="row" style={{ gap: 8, marginTop: 6 }}>
          <label>{t('sadCommentLabel')}
            <input value={comment} onChange={e => setComment(e.target.value)} maxLength={1000} />
          </label>
          <button type="button" className="btn small" disabled={busy || !comment.trim()}
                  onClick={() => decide(newest, 'rejected')}>{t('sadSend')}</button>
          <button type="button" className="btn small secondary"
                  onClick={() => { setRejecting(false); setComment('') }}>{t('sadCancel')}</button>
        </div>
      )}
      {comparing && <SadCompareModal batchId={batchId} draft={comparing}
                                     onClose={() => setComparing(null)} onCompared={load} />}
    </div>
  )
}
