import { UserIcon } from 'lucide-react'
import { useT } from '../../i18n'
import { formatDate, formatDateTime } from '../../dates'
import type { TransportJob } from '../../types'
import { JOB_CLASS, type OnAction } from './shared'
import ManageQuotes from './ManageQuotes'
import { ForwarderQuote } from './forms'

// Szczegóły zlecenia wyceny: nagłówek, KPI, kontenery + panel roli (spedytor / logistyka).
export default function JobDetail({ job, isForwarder, canManage, onAction, error, busy }: {
  job: TransportJob
  isForwarder: boolean
  canManage: boolean
  onAction: OnAction
  error: string
  busy: boolean
}) {
  const t = useT()
  return (
    <div className="panel">
      <div className="row row-between">
        <h2 className="m0">{t('quoteJob')} {job.number}</h2>
        <span className={`badge ${JOB_CLASS[job.status]}`}>{t(`job_${job.status}`)}</span>
      </div>
      <div className="detail-grid">
        <div className="item"><b>{t('quotePickup')}</b>{job.pickup_location || '—'}</div>
        <div className="item"><b>{t('quoteDelivery')}</b>{job.delivery_location || '—'}</div>
        <div className="item"><b>{t('quoteSent')}</b>{formatDateTime(job.sent_at)}</div>
        <div className="item"><b>{t('quoteDeadline')}</b>
          {job.response_deadline
            ? <span className={job.kpi.deadline_passed ? 'quote-late' : ''}>
                {formatDateTime(job.response_deadline)}
                {job.kpi.deadline_passed && ` · ${t('quoteDeadlinePassed')}`}
              </span>
            : `${job.response_hours} h`}
        </div>
        {/* SCFI i KPI to dane wewnętrzne — spedytor ich nie widzi (anchoring / liczba konkurencji) */}
        {!isForwarder && job.scfi_index && <div className="item"><b>SCFI</b>{job.scfi_index}</div>}
        {!isForwarder && job.status !== 'SZKIC' && (
          <div className="item"><b>{t('quoteKpi')}</b>
            {job.kpi.responded}/{job.kpi.invited} ({job.kpi.response_rate}%)
            {job.kpi.expired > 0 && ` · ${job.kpi.expired} ${t('quoteExpiredCnt')}`}
          </div>
        )}
        {job.note && <div className="item"><b>{t('notes')}</b>{job.note}</div>}
      </div>

      <h3>{t('poContainers')} ({job.container_count})</h3>
      <div className="table-scroll">
        <table className="grid">
          <thead><tr><th>{t('containerNo')}</th><th>{t('supplier')}</th>
            <th>{t('orderNumbers')}</th><th>{t('warehouse')}</th><th>{t('eta')}</th></tr></thead>
          <tbody>
            {job.containers.map(c => (
              <tr key={c.container_id}>
                <td className="mono strong">{c.container_no}</td>
                <td>
                  {c.supplier_name}
                  {c.supplier_contact_name && (
                    <div className="muted txt-sm">
                      <UserIcon size={14} /> {c.supplier_contact_name}
                      {c.supplier_contact_phone ? ` · ${c.supplier_contact_phone}` : ''}
                      {c.supplier_contact_email ? ` · ${c.supplier_contact_email}` : ''}
                    </div>
                  )}
                </td>
                <td className="mono">{c.order_numbers}</td>
                <td>{c.warehouse_name}</td>
                <td>{formatDate(c.eta)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {error && <p className="error">{error}</p>}

      {isForwarder
        ? <ForwarderQuote job={job} onAction={onAction} />
        : <ManageQuotes job={job} canManage={canManage} onAction={onAction} busy={busy} />}
    </div>
  )
}
