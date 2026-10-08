// Podejrzane przypięcia faktur (spec 2026-10-01-bramka-dokument-dostawa, PR 4): jednorazowy
// przegląd dokumentów wgranych przed bramką — do ręcznego przejrzenia, nic nie przenosi samo.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import type { Conformity } from '../../InvoiceConformityNote'

interface ReportRow {
  job_id: number
  container_id: number
  container_no: string
  filename: string
  invoice_number: string
  doc_kind: string
  confirmed: boolean
  status: 'uncertain' | 'conflict'
  signals: Conformity['signals']
  overage: boolean
  move_to: Conformity['move_to']
  ack: Conformity['ack']
}

interface Report { checked: number; rows: ReportRow[] }

export default function ConformityReportTab() {
  const t = useT()
  const [report, setReport] = useState<Report | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [onlyConflicts, setOnlyConflicts] = useState(true)

  const run = () => {
    setBusy(true)
    setError('')
    api.get<Report>('/api/invoice-conformity/report')
      .then(r => setReport(r && Array.isArray(r.rows) ? r : { checked: 0, rows: [] }))
      .catch(e => setError(errorMessage(e)))
      .finally(() => setBusy(false))
  }

  const why = (r: ReportRow) => {
    const bad = r.signals.filter(s => s.ok === false)
      .map(s => (s.detail ? `${t(`confSig_${s.key}`)}: ${s.detail}` : t(`confSig_${s.key}`)))
    if (bad.length) return bad.join('; ')
    const unknown = r.signals.filter(s => s.ok === null).map(s => t(`confSig_${s.key}`))
    if (r.overage) unknown.push(t('confOverage'))
    return `${t('confUncertain')} ${unknown.join(', ')}`
  }

  const rows = (report?.rows ?? []).filter(r => !onlyConflicts || r.status === 'conflict')
  return (
    <div className="panel">
      <h3>{t('confReportTitle')}</h3>
      <p className="muted" style={{ fontSize: 13 }}>{t('confReportHint')}</p>
      <div className="row" style={{ gap: 12, alignItems: 'center', marginBottom: 12 }}>
        <button className="btn" disabled={busy} onClick={run}>{busy ? t('confReportBusy') : t('confReportRun')}</button>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
          <input type="checkbox" checked={onlyConflicts} onChange={e => setOnlyConflicts(e.target.checked)} />
          {t('confReportOnlyConflicts')}
        </label>
        {report && <span className="muted">{t('confReportChecked').replace('{v}', String(report.checked))}</span>}
      </div>
      {error && <p className="error">{error}</p>}
      {report && rows.length === 0 && <p className="muted">{t('confReportEmpty')}</p>}
      {rows.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="grid">
            <thead>
              <tr>
                <th>{t('containerNo')}</th><th>{t('confReportDoc')}</th>
                <th>{t('confReportStatus')}</th><th>{t('confReportWhy')}</th><th>{t('confFitsTo')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.job_id}>
                  <td><Link to={`/kontenery/${r.container_id}`}>{r.container_no}</Link></td>
                  <td>{r.invoice_number || r.filename}
                    <div className="muted" style={{ fontSize: 11 }}>
                      {r.filename}{r.confirmed ? ` · ${t('invConfirmed1')}` : ''}
                    </div>
                  </td>
                  <td>
                    <span className={`badge ${r.status === 'conflict' ? 'st-OPOZNIONY' : 'st-ZREALIZOWANY'}`}>
                      {t(r.status === 'conflict' ? 'confReportConflict' : 'confReportUncertain')}
                    </span>
                  </td>
                  <td style={{ fontSize: 13 }}>{why(r)}
                    {r.ack && <div className="muted" style={{ fontSize: 11 }}>{t('confAcked')}: {r.ack.reason}</div>}
                  </td>
                  <td>{r.move_to.map(c => c.container_no).join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
