import { XIcon } from 'lucide-react'
import { useT } from '../../i18n'
import { formatNum } from '../../dates'
import type { CostRow, PerfRow } from './shared'
import CostTrend from './CostTrend'

// Raport kosztów (miesiąc × waluta) z trendem — panel prawej kolumny.
export function CostReport({ rows, onClose }: { rows: CostRow[]; onClose: () => void }) {
  const t = useT()
  return (
    <div className="panel">
      <div className="row row-between">
        <h2 className="m0">{t('quoteCostReport')}</h2>
        <button className="btn small" onClick={onClose} aria-label={t('close')} title={t('close')}><XIcon size={14} /></button>
      </div>
      {rows.length > 0 && <CostTrend rows={rows} />}
      <table className="grid report-table">
        <thead><tr><th>{t('quoteCostMonth')}</th><th>{t('zlCurrency')}</th>
          <th>{t('quoteCostTotal')}</th><th>{t('quoteCostCount')}</th></tr></thead>
        <tbody>
          {rows.length === 0
            ? <tr><td colSpan={4} className="muted">—</td></tr>
            : rows.map(r => (
                <tr key={`${r.month}-${r.currency}`}>
                  <td className="mono">{r.month}</td><td>{r.currency}</td>
                  <td className="mono strong">{formatNum(r.total)}</td>
                  <td>{r.count}</td>
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  )
}

// Raport skuteczności spedytorów (response/win rate, transit) — panel prawej kolumny.
export function PerfReport({ rows, onClose }: { rows: PerfRow[]; onClose: () => void }) {
  const t = useT()
  return (
    <div className="panel">
      <div className="row row-between">
        <h2 className="m0">{t('perfReport')}</h2>
        <button className="btn small" onClick={onClose} aria-label={t('close')} title={t('close')}><XIcon size={14} /></button>
      </div>
      <table className="grid report-table">
        <thead><tr>
          <th>{t('forwarder')}</th><th>{t('perfInvited')}</th><th>{t('perfResponded')}</th>
          <th>{t('perfResponseRate')}</th><th>{t('perfWon')}</th><th>{t('perfWinRate')}</th>
          <th>{t('perfNoEquip')}</th><th>{t('perfRolls')}</th><th>{t('perfAvgTransit')}</th>
        </tr></thead>
        <tbody>
          {rows.length === 0
            ? <tr><td colSpan={9} className="muted">—</td></tr>
            : rows.map(r => (
                <tr key={r.forwarder_id}>
                  <td className="strong">{r.forwarder}</td>
                  <td>{r.invited}</td><td>{r.responded}</td>
                  <td className="mono">{r.response_rate}%</td>
                  <td className="strong">{r.won}</td>
                  <td className="mono">{r.win_rate}%</td>
                  <td>{r.no_equipment || '—'}</td><td>{r.rolls || '—'}</td>
                  <td>{r.avg_transit != null ? `${r.avg_transit} d` : '—'}</td>
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  )
}
