import { BanIcon, StarIcon, TriangleAlertIcon, XIcon } from 'lucide-react'
import { useState } from 'react'
import { api } from '../../api'
import { useT } from '../../i18n'
import { formatDate, formatDateTime } from '../../dates'
import { Modal } from '../../components'
import type { Quote, QuoteRevision, TransportJob } from '../../types'
import { QUOTE_CLASS, money, type OnAction } from './shared'
import { AgentPanel, CancelBar } from './forms'

// Panel logistyki/admina: tabela ofert, wybór zwycięzcy, historia rewizji, anulowanie.
export default function ManageQuotes({ job, canManage, onAction, busy }: {
  job: TransportJob
  canManage: boolean
  onAction: OnAction
  busy: boolean
}) {
  const t = useT()
  const [history, setHistory] = useState<{ qid: number; items: QuoteRevision[] } | null>(null)
  const [chooseFor, setChooseFor] = useState<Quote | null>(null)
  const [reason, setReason] = useState('')
  const showHistory = (qid: number) => api
    .get<QuoteRevision[]>(`/api/transport-jobs/${job.id}/quotes/${qid}/history`)
    .then(items => setHistory({ qid, items })).catch(() => setHistory({ qid, items: [] }))
  const choose = (quoteId: number, why: string) =>
    onAction(() => api.post<TransportJob>(
      `/api/transport-jobs/${job.id}/choose`, { quote_id: quoteId, reason: why }))
  return (
    <>
      <div className="row row-between row-center">
        <h3 className="h3-block">{t('quoteOffers')} ({job.quotes.length})</h3>
        {canManage && job.status === 'SZKIC' && (
          <button className="btn" disabled={busy} onClick={() => onAction(() =>
            api.post<TransportJob>(`/api/transport-jobs/${job.id}/send`, {}))}>
            {t('quoteSend')}
          </button>
        )}
      </div>
      <div className="table-scroll">
        <table className="grid">
          <thead><tr><th>{t('forwarder')}</th><th>{t('quoteAmount')}</th><th>{t('carriers')}</th>
            <th>ETD</th><th>ETA</th><th>{t('zlTransit')}</th><th>{t('quoteFlags')}</th>
            <th>{t('status')}</th><th>{t('notes')}</th><th></th></tr></thead>
          <tbody>
            {job.quotes.map(q => (
              <tr key={q.id} className={q.id === job.chosen_quote_id ? 'quote-winner' : ''}>
                <td>
                  <b>{q.forwarder_name}</b>
                  {q.score != null && (
                    <div className="quote-score">
                      {q.recommended && <span className="badge st-ZREALIZOWANY"><StarIcon size={12} fill="currentColor" /> {t('quoteRecommended')}</span>}{' '}
                      <span className="muted">{t('quoteScore')}: {q.score}</span>
                    </div>
                  )}
                </td>
                <td className="mono strong">
                  {q.revised_amount != null ? (
                    <span title={q.revised_note || undefined}>
                      <s className="muted">{money(q)}</s>{' '}
                      <span className="quote-late"><TriangleAlertIcon size={14} /> {q.revised_amount} {q.currency}</span>
                    </span>
                  ) : money(q)}
                </td>
                <td>{q.carrier_name ?? '—'}</td>
                <td className="mono">{q.etd ? formatDate(q.etd) : '—'}</td>
                <td className="mono">{q.eta ? formatDate(q.eta) : '—'}</td>
                <td>{q.transit_time_days != null ? `${q.transit_time_days} ${t('zlDays')}` : '—'}</td>
                <td>
                  {q.no_equipment && <span className="badge cs-REWIZJA">{t('quoteNoEquip')}</span>}
                  {q.can_roll_booking && <span className="badge st-W_TRANSPORCIE">{t('quoteRoll')}</span>}
                  {!q.no_equipment && !q.can_roll_booking && '—'}
                </td>
                <td><span className={`badge ${QUOTE_CLASS[q.status]}`}>{t(`quote_${q.status}`)}</span></td>
                <td className="pre">{q.note}</td>
                <td>
                  {canManage && job.status === 'WYSLANE' && q.status === 'WYCENIONA' && (
                    <button className="btn small" disabled={busy} onClick={() => {
                      if (q.recommended) { choose(q.id, ''); return }
                      setReason(''); setChooseFor(q)
                    }}>
                      {t('quoteChoose')}
                    </button>
                  )}
                  {canManage && q.revised_amount != null && (
                    <button className="btn small" disabled={busy} onClick={() => onAction(() =>
                      api.post<TransportJob>(
                        `/api/transport-jobs/${job.id}/quotes/${q.id}/approve-price`, {}))}>
                      {t('quoteApprovePrice')}
                    </button>
                  )}
                  {q.submitted_at && (
                    <button className="btn small ghost" onClick={() => showHistory(q.id)}>
                      {t('quoteHistory')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {history && (
        <div className="panel history-panel">
          <div className="row row-between">
            <b>{t('quoteHistory')}</b>
            <button className="btn small" aria-label={t('close')} onClick={() => setHistory(null)}><XIcon size={14} /></button>
          </div>
          {history.items.length === 0
            ? <p className="muted history-empty">—</p>
            : <ul className="history-list">
                {history.items.map(r => (
                  <li key={r.id}>
                    <span className="mono">{formatDateTime(r.created_at)}</span> ·{' '}
                    <span className="badge cs-ZLECONA">{r.kind}</span>{' '}
                    <b>{r.amount != null ? `${r.amount} ${r.currency}` : '—'}</b>
                    {r.note ? ` · ${r.note}` : ''}
                    {r.created_by_login ? ` · ${r.created_by_login}` : ''}
                  </li>
                ))}
              </ul>}
        </div>
      )}
      {job.status === 'ANULOWANE' && (
        <div className="row cancel-row">
          {job.cancel_reason && (
            <p className="quote-late m0">
              <BanIcon size={14} /> {t('quoteCancelledReason')}: {job.cancel_reason}
            </p>
          )}
          {canManage && (
            <button className="btn small" disabled={busy} onClick={() => onAction(() =>
              api.post<TransportJob>(`/api/transport-jobs/${job.id}/reopen`, {}))}>
              {t('quoteReopen')}
            </button>
          )}
        </div>
      )}
      {canManage && job.status === 'ZLECONE' && <AgentPanel job={job} onAction={onAction} mode="logistics" />}
      {canManage && job.status !== 'ANULOWANE' && (
        <CancelBar job={job} onAction={onAction} />
      )}
      {chooseFor && (
        <Modal title={t('quoteChoose')} onClose={() => setChooseFor(null)}>
          <p className="mt0">
            <b>{chooseFor.forwarder_name}</b> — {money(chooseFor)}
          </p>
          <label>{t('quoteChoiceReason')} *
            <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} autoFocus />
          </label>
          <div className="actions modal-actions">
            <button className="btn" disabled={!reason.trim()} onClick={() => {
              choose(chooseFor.id, reason); setChooseFor(null)
            }}>
              {t('quoteChoose')}
            </button>
            <button className="btn small secondary" onClick={() => setChooseFor(null)}>
              {t('cancel')}
            </button>
          </div>
        </Modal>
      )}
    </>
  )
}
