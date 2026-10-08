import { useContext, useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { LangContext, localeFor, useT } from '../i18n'
import { useQueryParam, validDateRange } from '../urlState'
import { LoadError, Skeleton } from '../feedback'
import { formatDate } from '../dates'
import ForecastTab from './ForecastTab'
import StatsCharts from './StatsCharts'

interface WarehouseDay {
  warehouse_id: number
  name: string
  rail: number
  sea: number
  total: number
  limit: number | null
  over: boolean
}

interface AnalysisDay {
  day: string
  is_free_day: boolean
  warehouses: WarehouseDay[]
  total: number
}

interface AnalysisData {
  warehouses: { id: number; name: string }[]
  days: AnalysisDay[]
}

export default function AnalysisTab({ companyCode }: { companyCode: string }) {
  const t = useT()
  const { lang } = useContext(LangContext)
  const [view, setView] = useState<'analysis' | 'forecast' | 'trends'>('analysis')
  const [data, setData] = useState<AnalysisData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // zakres dat w URL (od/do, ISO); walidacja przy odczycie — zła/odwrócona data → domyślny
  const [odRaw, setDateFrom] = useQueryParam('od')
  const [doRaw, setDateTo] = useQueryParam('do')
  const [dateFrom, dateTo] = validDateRange(odRaw, doRaw)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let ignore = false  // spóźniona odpowiedź nie nadpisze danych dla nowszego zakresu
    setLoading(true)
    const params = new URLSearchParams({ company_code: companyCode })
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    api.get<AnalysisData>(`/api/analysis/unloading?${params}`)
      .then(d => { if (!ignore) { setData(d); setError('') } })
      .catch(err => { if (!ignore) { setData(null); setError(errorMessage(err)) } })
      .finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [companyCode, dateFrom, dateTo, reload])

  const weekday = (iso: string) =>
    new Intl.DateTimeFormat(localeFor(lang), { weekday: 'short' })
      .format(new Date(`${iso}T00:00:00`))

  const viewToggle = (
    <div className="seg" style={{ marginBottom: 10 }}>
      <button className={view === 'analysis' ? 'active' : ''}
              onClick={() => setView('analysis')}>{t('analysisView')}</button>
      <button className={view === 'forecast' ? 'active' : ''}
              onClick={() => setView('forecast')}>{t('forecastView')}</button>
      <button className={view === 'trends' ? 'active' : ''}
              onClick={() => setView('trends')}>{t('trendsView')}</button>
    </div>
  )
  if (view === 'forecast') return <div>{viewToggle}<ForecastTab companyCode={companyCode} /></div>
  if (view === 'trends') return <div>{viewToggle}<StatsCharts /></div>
  if (loading && !data) return <div>{viewToggle}<Skeleton rows={6} /></div>
  if (error) return <div>{viewToggle}<LoadError message={error} onRetry={() => setReload(n => n + 1)} /></div>
  if (!data || data.days.length === 0) return <div>{viewToggle}<p>{t('empty')}</p></div>

  return (
    <div>
      {viewToggle}
      <div className="filters">
        <label style={{ fontSize: 14 }}>{t('dateFrom')}{' '}
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
        </label>
        <label style={{ fontSize: 14 }}>{t('dateTo')}{' '}
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} />
        </label>
      </div>
      <div className="panel" style={{ padding: 0, overflowX: 'auto' }}>
        <table className="grid analysis-grid">
          <thead>
            <tr>
              <th rowSpan={2}>{t('dateFrom')}</th>
              <th rowSpan={2} aria-label="Dzień tygodnia" />
              {data.warehouses.map(w => (
                <th key={w.id} colSpan={4} className="wh-head">{w.name}</th>
              ))}
              <th rowSpan={2}>{t('dayTotal')}</th>
            </tr>
            <tr>
              {data.warehouses.map(w => (
                <FragmentHeaders key={w.id} />
              ))}
            </tr>
          </thead>
          <tbody>
            {data.days.map(day => (
              <tr key={day.day} className={day.is_free_day ? 'free-row' : ''}>
                <td className="mono">{formatDate(day.day)}</td>
                <td className={day.is_free_day ? 'free-cell' : ''}>{weekday(day.day)}</td>
                {day.warehouses.map(w => (
                  <WarehouseCells key={w.warehouse_id} w={w} />
                ))}
                <td className="strong">{day.total || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FragmentHeaders() {
  const t = useT()
  return (
    <>
      <th>{t('seaLbl')}</th>
      <th>{t('railLbl')}</th>
      <th>{t('sumLbl')}</th>
      <th>{t('limitLabel')}</th>
    </>
  )
}

function WarehouseCells({ w }: { w: WarehouseDay }) {
  return (
    <>
      <td>{w.sea || ''}</td>
      <td>{w.rail || ''}</td>
      <td className={`strong${w.over ? ' over-limit' : ''}`}>{w.total || ''}</td>
      <td className="muted">{w.limit ?? ''}</td>
    </>
  )
}
