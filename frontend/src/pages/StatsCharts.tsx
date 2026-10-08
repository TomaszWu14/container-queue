import { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { LoadError, Skeleton } from '../feedback'
import { formatDate } from '../dates'

// #56 + #58: trend transit time (linie SVG) i prognoza obłożenia (słupki SVG).
// Wykresy inline w stylu „konsoli operacyjnej" — hairline, tokeny z styles.css.

interface TrendPoint { month: string; avg_days: number; count: number }
interface TrendData {
  overall: TrendPoint[]
  by_port: { port: string; points: TrendPoint[] }[]
}
interface OccWeek { week_start: string; week_end: string; containers: number; pallets: number }

const W = 640, H = 220, PAD = { l: 36, r: 12, t: 12, b: 28 }
const LINE_COLORS = ['var(--accent-ink, #b07408)', '#2563eb', '#0e9488', '#9333ea']

/** Ostatnie 12 miesięcy jako "YYYY-MM" — wspólna oś X niezależna od dziur w danych. */
function last12Months(): string[] {
  const out: string[] = []
  const d = new Date()
  for (let i = 11; i >= 0; i--) {
    const m = new Date(d.getFullYear(), d.getMonth() - i, 1)
    out.push(`${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, '0')}`)
  }
  return out
}

function TransitTrendSection() {
  const t = useT()
  const [data, setData] = useState<TrendData | null>(null)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    api.get<TrendData>('/api/stats/transit-trend')
      .then(d => { setData(d); setError('') })
      .catch(err => setError(errorMessage(err)))
  }, [reload])

  if (error) return <LoadError message={error} onRetry={() => setReload(n => n + 1)} />
  if (!data) return <Skeleton rows={4} />
  if (data.overall.length === 0) return <p style={{ color: 'var(--muted)' }}>{t('empty')}</p>

  const months = last12Months()
  const series = [
    { name: t('trendOverall'), points: data.overall },
    ...data.by_port.map(p => ({ name: p.port, points: p.points })),
  ]
  const maxY = Math.max(1, ...series.flatMap(s => s.points.map(p => p.avg_days)))
  const x = (i: number) => PAD.l + (i * (W - PAD.l - PAD.r)) / Math.max(1, months.length - 1)
  const y = (v: number) => H - PAD.b - (v / maxY) * (H - PAD.t - PAD.b)
  const gridYs = [0, 0.5, 1].map(f => Math.round(maxY * f))

  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <h2>{t('trendTitle')}</h2>
      <p style={{ color: 'var(--muted)', fontSize: 13 }}>{t('trendInfo')}</p>
      <div className="row" style={{ gap: 14, flexWrap: 'wrap', fontSize: 13, marginBottom: 6 }}>
        {series.map((s, si) => (
          <span key={s.name} className="row" style={{ gap: 6, alignItems: 'center' }}>
            <span style={{ width: 14, height: 3, background: LINE_COLORS[si], display: 'inline-block' }} />
            {s.name}
          </span>
        ))}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: 760 }} role="img"
             aria-label={t('trendTitle')}>
          {gridYs.map(v => (
            <g key={v}>
              <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)}
                    stroke="var(--border, #e2e8f0)" strokeWidth="1" />
              <text x={PAD.l - 6} y={y(v) + 4} textAnchor="end" fontSize="10"
                    fill="var(--muted, #64748b)">{v}</text>
            </g>
          ))}
          {months.map((m, i) => i % 2 === 0 && (
            <text key={m} x={x(i)} y={H - 8} textAnchor="middle" fontSize="10"
                  fill="var(--muted, #64748b)">{m.slice(2)}</text>
          ))}
          {series.map((s, si) => {
            const pts = months
              .map((m, i) => ({ i, p: s.points.find(q => q.month === m) }))
              .filter((v): v is { i: number; p: TrendPoint } => v.p != null)
            return (
              <g key={s.name}>
                <polyline fill="none" stroke={LINE_COLORS[si]} strokeWidth="2"
                          points={pts.map(v => `${x(v.i)},${y(v.p.avg_days)}`).join(' ')} />
                {pts.map(v => (
                  <circle key={v.i} cx={x(v.i)} cy={y(v.p.avg_days)} r="2.6" fill={LINE_COLORS[si]}>
                    <title>{`${s.name} ${months[v.i]}: ${v.p.avg_days} d (n=${v.p.count})`}</title>
                  </circle>
                ))}
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}

function OccupancySection() {
  const t = useT()
  const [weeks, setWeeks] = useState<OccWeek[] | null>(null)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    api.get<{ weeks: OccWeek[] }>('/api/stats/occupancy-forecast')
      .then(d => { setWeeks(d.weeks); setError('') })
      .catch(err => setError(errorMessage(err)))
  }, [reload])

  if (error) return <LoadError message={error} onRetry={() => setReload(n => n + 1)} />
  if (!weeks) return <Skeleton rows={4} />

  const maxC = Math.max(1, ...weeks.map(w => w.containers))
  const maxP = Math.max(1, ...weeks.map(w => w.pallets))
  const bw = 46, gap = 110

  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <h2>{t('occTitle')}</h2>
      <div className="row" style={{ gap: 14, fontSize: 13, marginBottom: 6 }}>
        <span className="row" style={{ gap: 6, alignItems: 'center' }}>
          <span style={{ width: 12, height: 12, background: 'var(--accent, #f5a623)', display: 'inline-block', borderRadius: 3 }} />
          {t('occContainers')}
        </span>
        <span className="row" style={{ gap: 6, alignItems: 'center' }}>
          <span style={{ width: 12, height: 12, background: '#2563eb', display: 'inline-block', borderRadius: 3 }} />
          {t('occPallets')}
        </span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <svg viewBox={`0 0 ${gap * 4 + 40} 200`} style={{ width: '100%', maxWidth: 560 }} role="img"
             aria-label={t('occTitle')}>
          {weeks.map((w, i) => {
            const x0 = 20 + i * gap
            const hC = (w.containers / maxC) * 130
            const hP = (w.pallets / maxP) * 130
            return (
              <g key={w.week_start}>
                <rect x={x0} y={160 - hC} width={bw} height={hC} rx="2" fill="var(--accent, #f5a623)">
                  <title>{`${t('occContainers')}: ${w.containers}`}</title>
                </rect>
                <rect x={x0 + bw + 4} y={160 - hP} width={bw} height={hP} rx="2" fill="#2563eb">
                  <title>{`${t('occPallets')}: ${w.pallets}`}</title>
                </rect>
                <text x={x0} y={160 - hC - 4} fontSize="11" fill="var(--text, #0f172a)">{w.containers}</text>
                <text x={x0 + bw + 4} y={160 - hP - 4} fontSize="11" fill="var(--text, #0f172a)">{w.pallets}</text>
                <text x={x0 + bw} y={178} textAnchor="middle" fontSize="10"
                      fill="var(--muted, #64748b)" className="mono">
                  {formatDate(w.week_start).slice(0, 5)}–{formatDate(w.week_end).slice(0, 5)}
                </text>
              </g>
            )
          })}
          <line x1="12" x2={gap * 4 + 28} y1="160" y2="160" stroke="var(--border, #e2e8f0)" />
        </svg>
      </div>
    </div>
  )
}

export default function StatsCharts() {
  return (
    <div>
      <TransitTrendSection />
      <OccupancySection />
    </div>
  )
}
