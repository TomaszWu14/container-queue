import { useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api'
import { LangContext, localeFor, useT } from '../i18n'
import { LoadError, Skeleton } from '../feedback'
import { formatDate } from '../dates'

interface ForecastDay {
  date: string
  is_free_day: boolean
  containers: number
  limit: number | null
  over: boolean
  pallets: number | null
  pallets_estimated: boolean
  container_ids: number[]
}

interface ForecastData {
  date_from: string
  date_to: string
  warehouses: { id: number; name: string; days: ForecastDay[] }[]
}

/** Wykres słupkowy zajętości 28 dni jednego magazynu: dostawy/dzień vs limit dnia
    (z nadpisaniami per-datę — dane z /analysis/forecast, które już je liczy).
    Przekroczenia limitu na czerwono; linia = limit. Czysty SVG, bez bibliotek. */
function OccupancyBars({ name, days }: { name: string; days: ForecastDay[] }) {
  const t = useT()
  const shown = days.slice(0, 28)
  const maxVal = Math.max(1, ...shown.map(d => Math.max(d.containers, d.limit ?? 0)))
  const W = 24, GAP = 6, H = 120, PAD = 18   // szerokość słupka / odstęp / wysokość
  const width = shown.length * (W + GAP) + GAP
  const y = (v: number) => H - (v / maxVal) * (H - 8)
  return (
    <div style={{ marginBottom: 14 }}>
      <div className="strong" style={{ marginBottom: 4 }}>{name}</div>
      <div style={{ overflowX: 'auto' }}>
        <svg width={width} height={H + PAD} role="img"
             aria-label={`${t('fcChartTitle')} — ${name}`}>
          {shown.map((d, i) => {
            const x = GAP + i * (W + GAP)
            const barH = Math.max(1, H - y(d.containers))
            return (
              <g key={d.date}>
                {d.is_free_day && (
                  <rect x={x - GAP / 2} y={0} width={W + GAP} height={H}
                        fill="var(--free-day, #fdf2f2)" />
                )}
                {d.containers > 0 && (
                  <rect x={x} y={y(d.containers)} width={W} height={barH}
                        fill={d.over ? '#c0392b' : '#0b5fff'} rx={2}>
                    <title>{`${formatDate(d.date)}: ${d.containers}${d.limit != null ? ` / limit ${d.limit}` : ''}`}</title>
                  </rect>
                )}
                {d.limit != null && (
                  <line x1={x - 2} x2={x + W + 2} y1={y(d.limit)} y2={y(d.limit)}
                        stroke="#334155" strokeWidth={2} strokeDasharray="3 2" />
                )}
                <text x={x + W / 2} y={H + 12} textAnchor="middle"
                      fontSize={9} fill="var(--muted, #6b7a90)">
                  {formatDate(d.date).slice(0, 5)}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}

/** Prognoza obciążenia magazynów (Analityka F2): heatmapa 4 tyg. w przód.
    Kolor komórki wg % limitu; palety jako druga liczba („~" = szacunek). */
interface StaffingDay {
  day: string
  containers: number
  container_pallets: number
  call_pallets: number
  total_pallets: number
  suggested_people: number
}

// #66: kafel predykcji obsady — palety jutro/pojutrze ÷ palety/os./zmianę (env, domyślnie 40)
function StaffingTile() {
  const t = useT()
  const [data, setData] = useState<{ pallets_per_person: number; days: StaffingDay[] } | null>(null)
  useEffect(() => {
    api.get<{ pallets_per_person: number; days: StaffingDay[] }>('/api/warehouse/staffing')
      .then(setData).catch(() => setData(null))
  }, [])
  if (!data) return null
  const labels = [t('staffTomorrow'), t('staffDayAfter')]
  return (
    <div className="panel" style={{ marginBottom: 12 }} data-testid="staffing-tile">
      <b>{t('staffTitle')}</b>
      <span className="muted" style={{ marginLeft: 8, fontSize: 13 }}>
        ({data.pallets_per_person} {t('staffPerPerson')})
      </span>
      <div className="row" style={{ gap: 24, marginTop: 8, flexWrap: 'wrap' }}>
        {data.days.map((d, i) => (
          <div key={d.day}>
            <div className="muted" style={{ fontSize: 13 }}>
              {labels[i] ?? d.day} · {formatDate(d.day)}
            </div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              {d.suggested_people} {t('staffPeople')}
            </div>
            <div className="muted" style={{ fontSize: 13 }}>
              {d.total_pallets} {t('staffPallets')} · {d.containers} kont.
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ForecastTab({ companyCode }: { companyCode: string }) {
  const t = useT()
  const { lang } = useContext(LangContext)
  const navigate = useNavigate()
  const [data, setData] = useState<ForecastData | null>(null)
  const [error, setError] = useState('')
  const [week, setWeek] = useState(0)   // przesuwanie oknem tygodniowym (0..3)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    api.get<ForecastData>(`/api/analysis/forecast?company_code=${companyCode}`)
      .then(d => { setData(d); setError('') })
      .catch(err => setError(errorMessage(err)))
  }, [companyCode, reload])

  if (error) return <LoadError message={error} onRetry={() => setReload(n => n + 1)} />
  if (!data) return <Skeleton rows={6} />
  if (data.warehouses.length === 0) return <p style={{ color: 'var(--muted)' }}>{t('empty')}</p>

  const days = data.warehouses[0].days
  const visible = [...Array(14)].map((_, i) => week * 7 + i).filter(i => i < days.length)
  const weekday = (iso: string) =>
    new Intl.DateTimeFormat(localeFor(lang), { weekday: 'short' })
      .format(new Date(`${iso}T00:00:00`))

  const cellClass = (d: ForecastDay) => {
    if (d.containers === 0) return ''
    if (d.limit == null) return 'fc-ok'
    if (d.over) return 'fc-over'
    if (d.containers >= d.limit * 0.8) return 'fc-warn'
    return 'fc-ok'
  }

  return (
    <div>
      <StaffingTile />
      <div className="row" style={{ marginBottom: 10, gap: 10 }}>
        <div className="range-stepper">
          <button className="step" disabled={week === 0} aria-label={t('weekPrev')} onClick={() => setWeek(w => w - 1)}>‹</button>
          <span className="range-label">
            {formatDate(days[visible[0]]?.date)} → {formatDate(days[visible[visible.length - 1]]?.date)}
          </span>
          <button className="step" disabled={(week + 2) * 7 >= days.length}
                  aria-label={t('weekNext')} onClick={() => setWeek(w => w + 1)}>›</button>
        </div>
        <span style={{ color: 'var(--muted)', fontSize: 13 }}>{t('forecastInfo')}</span>
      </div>
      <div className="row" style={{ gap: 14, marginBottom: 10, fontSize: 13, flexWrap: 'wrap' }}>
        <span className="row" style={{ gap: 6, alignItems: 'center' }}>
          <span className="fc-cell fc-ok" style={{ width: 14, height: 14, display: 'inline-block', borderRadius: 3 }} />
          {t('fcLegendOk')}
        </span>
        <span className="row" style={{ gap: 6, alignItems: 'center' }}>
          <span className="fc-cell fc-warn" style={{ width: 14, height: 14, display: 'inline-block', borderRadius: 3 }} />
          {t('fcLegendWarn')}
        </span>
        <span className="row" style={{ gap: 6, alignItems: 'center' }}>
          <span className="fc-cell fc-over" style={{ width: 14, height: 14, display: 'inline-block', borderRadius: 3 }} />
          {t('fcLegendOver')}
        </span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="grid analysis-grid forecast-grid">
          <thead>
            <tr>
              <th>{t('warehouse')}</th>
              {visible.map(i => (
                <th key={days[i].date} className="wh-head"
                    style={days[i].is_free_day ? { background: '#fdf2f2' } : undefined}>
                  {weekday(days[i].date)}<br />
                  <span className="mono" style={{ fontWeight: 400 }}>{formatDate(days[i].date).slice(0, 5)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.warehouses.map(w => (
              <tr key={w.id}>
                <td className="strong">{w.name}</td>
                {visible.map(i => {
                  const d = w.days[i]
                  return (
                    <td key={d.date} className={`fc-cell ${cellClass(d)}`}
                        title={d.limit != null ? `limit ${d.limit}` : ''}
                        style={{ cursor: d.containers ? 'pointer' : 'default' }}
                        onClick={() => d.container_ids[0]
                          && navigate(`/kontenery/${d.container_ids[0]}`)}>
                      {d.containers > 0 && (
                        <>
                          <b>{d.containers}</b>{d.limit != null && <span className="muted">/{d.limit}</span>}
                          {d.pallets != null && (
                            <div className="muted" style={{ fontSize: 11 }}>
                              {d.pallets_estimated ? '~' : ''}{d.pallets} pal.
                            </div>
                          )}
                          {d.container_ids.length > 1 && (
                            <div className="muted" style={{ fontSize: 11 }}>
                              +{d.container_ids.length - 1} {t('fcMore')}
                            </div>
                          )}
                        </>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* prognoza zajętości 28 dni — słupki dostaw vs limit dnia per magazyn */}
      <div style={{ marginTop: 18 }}>
        <h3 style={{ margin: '0 0 2px' }}>{t('fcChartTitle')}</h3>
        <p className="muted" style={{ fontSize: 13, margin: '0 0 10px' }}>{t('fcChartHint')}</p>
        {data.warehouses.map(w => (
          <OccupancyBars key={w.id} name={w.name} days={w.days} />
        ))}
      </div>
    </div>
  )
}
