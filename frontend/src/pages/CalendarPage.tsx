// Kalendarz awizacji — makieta Claude Design „Kalendarz awizacji" (2026-09-24): KPI miesiąca,
// filtr magazynu, siatka tygodni z kartami dni (pierścień obłożenia + sloty per magazyn)
// i panel wybranego dnia; widok roku (agregat /api/calendar/year). Stan w URL:
// ?widok=rok&rok=2026 | ?widok=miesiac&rok=2026&miesiac=09[&dzien=2026-09-14]; bez parametrów = bieżący miesiąc.
import { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { WarehouseIcon } from 'lucide-react'
import { useUser } from '../userContext'
import { api, errorMessage } from '../api'
import { useDicts } from '../components'
import { formatDate, isoWeek, monthRangeYM, todayISO } from '../dates'
import { holidayName } from '../holidays'
import { EmptyState, LoadError, Skeleton } from '../feedback'
import { LangContext, localeFor, useT } from '../i18n'
import type { QueueDay } from '../types'
import { dayStat, etaIndex, monthWeeks, pct, totals, whName } from './calendar/calModel'
import DayCard from './calendar/DayCard'
import DayPanel from './calendar/DayPanel'
import YearView, { type YearAgg } from './calendar/YearView'

export default function CalendarPage() {
  const t = useT()
  const role = useUser()?.role
  const { lang } = useContext(LangContext)
  const dicts = useDicts()
  const now = new Date()
  const [sp, setSp] = useSearchParams()
  const num = (k: string, lo: number, hi: number) => {
    const v = Number(sp.get(k))
    return Number.isInteger(v) && v >= lo && v <= hi ? v : null
  }
  const year = num('rok', 2000, 2100) ?? now.getFullYear()
  const month = (num('miesiac', 1, 12) ?? now.getMonth() + 1) - 1
  const view: 'rok' | 'miesiac' = sp.get('widok') === 'rok' ? 'rok' : 'miesiac'
  const go = (v: 'rok' | 'miesiac', y: number, m = month, dzien?: string) => setSp(v === 'rok'
    ? { widok: 'rok', rok: String(y) }
    : { widok: 'miesiac', rok: String(y), miesiac: String(m + 1).padStart(2, '0'), ...(dzien ? { dzien } : {}) })
  const [wh, setWh] = useState('')          // '' = wszystkie magazyny
  const [sel, setSel] = useState(sp.get('dzien') ?? todayISO())
  const [days, setDays] = useState<QueueDay[]>([])
  const [agg, setAgg] = useState<YearAgg | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  const loadSeq = useRef(0)
  const load = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams({ date_from: monthRangeYM(year, 0)[0], date_to: monthRangeYM(year, 11)[1] })
    const seq = ++loadSeq.current
    // widok roku: jeden agregat (bez rekordów); miesiąc: pełne dni z /api/queue (jak dotąd)
    const req = view === 'rok'
      ? api.get<YearAgg>(`/api/calendar/year?rok=${year}`).then(d => { if (seq === loadSeq.current) setAgg(d) })
      : api.get<QueueDay[]>(`/api/queue?${params}`).then(d => { if (seq === loadSeq.current) setDays(d) })
    req.then(() => { if (seq === loadSeq.current) setLoadError('') })
      .catch(err => { if (seq === loadSeq.current) setLoadError(errorMessage(err)) })
      .finally(() => { if (seq === loadSeq.current) setLoading(false) })
  }, [year, view])
  useEffect(() => { load() }, [load])
  // klik dnia w widoku roku → zaznacz dzień i przewiń do jego karty
  const dzien = sp.get('dzien')
  useEffect(() => {
    if (!dzien || view !== 'miesiac' || loading) return
    setSel(dzien)
    document.querySelector(`.cal2-day[aria-label^="${dzien}"]`)?.scrollIntoView?.({ block: 'center' })
  }, [dzien, view, loading])

  // błąd bez danych: nie rysuj KPI ani siatki z zerami — wyglądają jak prawdziwe (audyt C4)
  const noData = view === 'rok' ? !agg : days.length === 0
  const failed = !!loadError && noData

  const byDate = useMemo(() => new Map(days.map(d => [d.day, d])), [days])
  const eta = useMemo(() => etaIndex(days), [days])
  // magazyny z limitem dziennym: te, do których w roku są awizacje (np. ACME, DLT)
  const whs = useMemo(() => {
    const used = new Set((view === 'rok'
      ? (agg?.days ?? []).map(r => (r.warehouse ?? '').toUpperCase())
      : days.flatMap(d => d.containers.map(whName))).filter(Boolean))
    const list = dicts.warehouses.filter(w => used.has(w.name.toUpperCase()))
    return list.map(w => ({ key: w.name.toUpperCase(), limit: w.default_daily_limit }))
      .sort((a, b) => a.key.localeCompare(b.key)).reverse()
  }, [days, agg, view, dicts.warehouses])
  const stat = useCallback((iso: string) => dayStat(byDate.get(iso), whs, eta.get(iso), wh),
    [byDate, whs, eta, wh])

  const weeks = useMemo(() => monthWeeks(year, month), [year, month])
  const monthDays = weeks.flat().filter((d): d is string => !!d)
  const mTot = totals(monthDays.map(stat))
  // C9: bez magazynów z limitem i bez awizacji → jeden komunikat zamiast siatki „0 /0”
  // (awizacje do magazynu bez limitu nadal widać w siatce — nie chowamy danych)
  const noCapacity = view === 'miesiac' && !loading && !failed && mTot.cap === 0 && mTot.bookings === 0
  const holidays = monthDays.filter(d => holidayName(d))
  const monthLabel = new Date(Date.UTC(year, month, 1)).toLocaleDateString(localeFor(lang), { month: 'long', timeZone: 'UTC' })
  const weekdays = [t('mo'), t('tu'), t('we'), t('th'), t('fr'), t('sa'), t('su')]
  const today = todayISO()
  const step = (by: number) => {
    const m = month + by
    go('miesiac', year + Math.floor(m / 12), ((m % 12) + 12) % 12)
  }

  const kpis = [
    { label: t('calKpiMonthBookings'), value: mTot.bookings, sub: `${t('calCapacity')} ${mTot.cap}` },
    { label: t('calKpiUtilization'), value: `${pct(mTot.bookings, mTot.cap)}%`, sub: whs.map(w => w.key).join(' + ') },
    { label: t('calKpiOverDays'), value: mTot.overDays, sub: t('calOfWorkdays').replace('{n}', String(mTot.workdays)), tone: mTot.overDays ? 'bad' : '' },
    { label: t('calKpiFreeSlots'), value: mTot.free, sub: t('calOfCapacity').replace('{n}', String(mTot.cap)) },
    { label: t('calKpiLate'), value: mTot.late, sub: t('calDemurrageRisk'), tone: mTot.late ? 'bad' : '' },
    { label: t('calKpiCustomsOpen'), value: mTot.customsOpen, sub: t('calCustomsOpenSub'), tone: mTot.customsOpen ? 'warn' : '' },
    { label: t('calKpiCalls'), value: mTot.calls, sub: t('calCallsSub') },
    { label: t('calKpiHolidays'), value: holidays.length, sub: holidays.map(d => formatDate(d)).join(', ') || '—' },
  ]

  const monthView = (
    <div className="cal2-layout">
      <div className="cal2-month">
        <div className="cal2-bar">
          <button onClick={() => step(-1)} aria-label={t('prevMonth')}>‹</button>
          <div className="cal2-bar-name">{monthLabel} <span className="mono">{year}</span></div>
          <button className="cal2-today" onClick={() => { go('miesiac', now.getFullYear(), now.getMonth()); setSel(today) }}>{t('calToday')}</button>
          <button onClick={() => step(1)} aria-label={t('nextMonth')}>›</button>
        </div>
        <div className="cal2-grid">
          <div className="cal2-wd" />
          {weekdays.map(w => <div key={w} className="cal2-wd">{w}</div>)}
          {weeks.map((wk, wi) => {
            const inMonth = wk.filter((d): d is string => !!d)
            const wt = totals(inMonth.map(stat))
            return [
              <div key={`w${wi}`} className="cal2-week">
                <b className="mono">T{isoWeek(inMonth[0])}</b>
                <span className="mono">{wt.bookings} {t('calAwiz')}</span>
                <span className="mono">{pct(wt.bookings, wt.cap)}%</span>
                {wt.overDays > 0 && <span className="bad">{wt.overDays} {t('calOverDays')}</span>}
              </div>,
              ...wk.map((iso, di) => iso
                ? <DayCard key={iso} iso={iso} s={stat(iso)} holiday={holidayName(iso)} selected={iso === sel}
                           today={iso === today} onSelect={setSel} />
                : <div key={`e${wi}-${di}`} className="cal2-day empty" />),
            ]
          })}
        </div>
      </div>
      <DayPanel iso={sel} info={byDate.get(sel)} s={stat(sel)} holiday={holidayName(sel)} />
    </div>
  )

  return (
    <main className="page cal2">
      <div className="cal2-head">
        <div>
          <div className="cal-eyebrow">{t('calEyebrow')}</div>
          <h1 className="cal-title">{t('calTitle')}</h1>
        </div>
        <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
          <span className="muted cal2-lbl">{t('warehouse')}</span>
          <div className="seg">
            <button className={wh === '' ? 'active' : ''} onClick={() => setWh('')}>{t('calAllWh')}</button>
            {whs.map(w => <button key={w.key} className={wh === w.key ? 'active' : ''} onClick={() => setWh(w.key)}>{w.key}</button>)}
          </div>
          <div className="seg">
            <button className={view === 'rok' ? 'active' : ''} onClick={() => go('rok', year)}>{t('calViewYear')}</button>
            <button className={view === 'miesiac' ? 'active' : ''} onClick={() => go('miesiac', year)}>{t('calViewMonth')}</button>
          </div>
        </div>
      </div>
      {view === 'miesiac' && !noCapacity && <div className="cal2-legend muted">
        <span><i className="lg-ring" />{t('calLegLoad')}</span>
        {whs.map(w => <span key={w.key}><i className={`lg-dot wh-${w.key.toLowerCase()}`} />{w.key}</span>)}
        <span><i className="lg-dot" />{t('calLegFreeSlot')}</span>
        <span><i className="lg-dot over" />{t('calLegOverLimit')}</span>
      </div>}
      {view === 'miesiac' && !failed && !noCapacity && (
        <div className="cal2-kpis">
          {kpis.map(k => (
            <div key={k.label} className="cal2-kpi">
              <small title={k.label}>{k.label}</small>
              <b className={`mono ${k.tone ?? ''}`}>{k.value}</b>
              <span className="muted">{k.sub}</span>
            </div>
          ))}
        </div>
      )}
      {loadError && <LoadError message={loadError} onRetry={load} />}
      {failed ? null
        : noCapacity ? (
          <EmptyState icon={WarehouseIcon} title={t('calNoCapacityTitle')} hint={t('calNoCapacityHint')}>
            {(role === 'admin' || role === 'logistics') &&
              <Link className="btn small secondary" to="/master-data/magazyny">{t('calNoCapacityLink')}</Link>}
          </EmptyState>
        )
        : loading && noData ? <Skeleton rows={6} />
        : view === 'miesiac' ? monthView
        : <YearView year={year} agg={agg} filter={wh} onYear={d => go('rok', year + d)}
                    onOpen={(m, iso) => go('miesiac', year, m, iso)} />}
    </main>
  )
}
