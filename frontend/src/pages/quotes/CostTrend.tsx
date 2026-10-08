import { useT } from '../../i18n'
import { formatNum } from '../../dates'
import type { CostRow } from './shared'

// Prosty wykres trendu kosztów — słupki znormalizowane per waluta (bez zewn. bibliotek).
export default function CostTrend({ rows }: { rows: CostRow[] }) {
  const t = useT()
  const data = [...rows].reverse()   // chronologicznie (rosnąco)
  const maxByCcy: Record<string, number> = {}
  data.forEach(r => { maxByCcy[r.currency] = Math.max(maxByCcy[r.currency] ?? 0, r.total) })
  return (
    <div className="cost-trend">
      <div className="muted cost-trend-title">{t('costTrend')}</div>
      <div className="cost-trend-rows">
        {data.map(r => (
          <div key={`${r.month}-${r.currency}`} className="cost-trend-row">
            <span className="mono cost-trend-label">{r.month} {r.currency}</span>
            <span className="cost-trend-track">
              <span className="cost-trend-bar"
                    style={{ width: `${Math.max(2, r.total / (maxByCcy[r.currency] || 1) * 100)}%` }} />
            </span>
            <span className="mono strong cost-trend-value">{formatNum(r.total)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
