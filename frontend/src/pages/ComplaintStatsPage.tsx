import { DownloadIcon } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, downloadCsv, errorMessage } from '../api'
import { useT } from '../i18n'
import type { ComplaintStats, ComplaintStatsRow } from '../types'
import { LoadError, Skeleton } from '../feedback'
import { statsToCsv } from './complaintUtils'

// W11 #68/#71: rejestr szkód — % kontenerów z reklamacją per dostawca/armator
// (ostatnie 12 mies.), sortowanie po kliknięciu nagłówka, eksport CSV, koszty.
type SortKey = keyof ComplaintStatsRow

function StatsTable({ title, rows, t }: {
  title: string
  rows: ComplaintStatsRow[]
  t: (k: string) => string
}) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'pct', desc: true })
  const sorted = useMemo(() => [...rows].sort((a, b) => {
    const va = a[sort.key], vb = b[sort.key]
    const cmp = typeof va === 'number' && typeof vb === 'number'
      ? va - vb : String(va).localeCompare(String(vb))
    return sort.desc ? -cmp : cmp
  }), [rows, sort])
  const header = (key: SortKey, label: string) => (
    <th className="clickable" style={{ cursor: 'pointer' }}
        onClick={() => setSort(s => ({ key, desc: s.key === key ? !s.desc : true }))}>
      {label}{sort.key === key ? (sort.desc ? ' ↓' : ' ↑') : ''}
    </th>
  )
  return (
    <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
      <h3 style={{ padding: '12px 14px 0' }}>{title}</h3>
      {rows.length === 0
        ? <p style={{ color: 'var(--muted)', padding: '0 14px 14px' }}>{t('complaintStatsEmpty')}</p>
        : (
          <table className="grid">
            <thead>
              <tr>
                {header('name', title)}
                {header('containers', t('complaintStatsContainers'))}
                {header('with_complaint', t('complaintStatsWith'))}
                {header('pct', t('complaintStatsPct'))}
              </tr>
            </thead>
            <tbody>
              {sorted.map(r => (
                <tr key={r.name}>
                  <td className="strong">{r.name}</td>
                  <td>{r.containers}</td>
                  <td>{r.with_complaint}</td>
                  <td className={r.pct >= 25 ? 'over-limit' : ''}>{r.pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </div>
  )
}

export default function ComplaintStatsPage() {
  const t = useT()
  const [stats, setStats] = useState<ComplaintStats | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    setError('')
    api.get<ComplaintStats>('/api/complaints/stats')
      .then(setStats).catch(err => setError(errorMessage(err)))
  }, [])
  useEffect(() => load(), [load])

  const exportCsv = () => {
    if (!stats) return
    const csv = statsToCsv(stats, {
      supplier: t('complaintStatsSupplier'), carrier: t('complaintStatsCarrier'),
      containers: t('complaintStatsContainers'), withComplaint: t('complaintStatsWith'),
      pct: t('complaintStatsPct'), currency: t('complaintCurrency'),
      claim: t('complaintStatsClaims'), recovered: t('complaintStatsRecovered'),
      recoveryPct: t('complaintStatsRecovery'),
    })
    downloadCsv('rejestr-szkod.csv', csv)
  }

  if (error) return <main className="page"><LoadError message={error} onRetry={load} /></main>
  if (!stats) return <main className="page"><Skeleton rows={6} /></main>

  return (
    <main className="page">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h2 style={{ fontSize: 19, margin: 0 }}>
          {t('complaintStats')}{' '}
          <span className="muted" style={{ fontSize: 14 }}>
            ({t('complaintStatsMonths').replace('{n}', String(stats.months))})
          </span>
        </h2>
        <button className="btn small secondary" onClick={exportCsv}><DownloadIcon size={14} /> {t('complaintStatsCsv')}</button>
      </div>
      {stats.costs.length > 0 && (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>{t('complaintCosts')}</h3>
          <table className="grid">
            <thead>
              <tr>
                <th>{t('complaintCurrency')}</th><th>{t('complaintStatsClaims')}</th>
                <th>{t('complaintStatsRecovered')}</th><th>{t('complaintStatsRecovery')}</th>
              </tr>
            </thead>
            <tbody>
              {stats.costs.map(c => (
                <tr key={c.currency}>
                  <td className="mono strong">{c.currency}</td>
                  <td>{c.claim.toFixed(2)}</td>
                  <td>{c.recovered.toFixed(2)}</td>
                  <td>{c.recovery_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <StatsTable title={t('complaintStatsSupplier')} rows={stats.suppliers} t={t} />
      <StatsTable title={t('complaintStatsCarrier')} rows={stats.carriers} t={t} />
    </main>
  )
}
