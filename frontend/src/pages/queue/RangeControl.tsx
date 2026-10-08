// Zakres dat kolejki (Kolejka Enterprise): Dziś / Tydzień / Miesiąc / Zakres (+ Wszystko w archiwum),
// stepper ‹ tydzień/miesiąc ›, „Od dziś" i pola od/do. Wyniesione z QueueFilterBar do paska filtrów.
import { useContext, useMemo } from 'react'
import {
  formatDateRange, isoWeek, isoWeekMonday, isoWeeksInYear, isoWeekYear, monthRange, parseISO,
  shiftDays, shiftMonth, todayISO, weekRange,
} from '../../dates'
import { LangContext, localeFor, useT } from '../../i18n'
import { RANGE_LABEL } from './config'
import type { RangeMode } from './config'
import type { QueueFilters } from './useQueueFilters'

export default function RangeControl({ f, archive }: { f: QueueFilters; archive: boolean }) {
  const t = useT()
  const { lang } = useContext(LangContext)
  const { rangeMode, setRangeMode, anchor, setAnchor } = f
  const today = todayISO()
  const isToday = rangeMode === 'custom' && f.dateFrom === today && f.dateTo === today

  const locale = localeFor(lang)
  // rok tygodnia ISO (nie kalendarzowy) — spójne opcje i skok na przełomie roku
  const anchorYear = isoWeekYear(anchor)
  const currentWeek = isoWeek(weekRange(anchor)[0])
  // krok w tył/przód po miesiącach lub tygodniach (wg trybu)
  const step = (dir: 1 | -1) =>
    setAnchor(rangeMode === 'month' ? shiftMonth(anchor, dir) : shiftDays(anchor, 7 * dir))
  const rangeLabel = useMemo(() => {
    if (rangeMode === 'month') {
      const [fr] = monthRange(anchor)
      const m = new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' }).format(parseISO(fr))
      return m.charAt(0).toUpperCase() + m.slice(1)
    }
    if (rangeMode === 'week') {
      const [fr, t2] = weekRange(anchor)
      return `${t('weekShort')} ${isoWeek(fr)} · ${formatDateRange(fr, t2, true)}`
    }
    return ''
  }, [rangeMode, anchor, locale, t])

  return (
    <>
      {/* Kolejka Enterprise: Dziś / Tydzień / Miesiąc / Zakres (archiwum dodatkowo „Wszystko") */}
      <div className="seg" role="group" aria-label={t('kqRange')}>
        {archive && (
          <button type="button" className={rangeMode === 'all' ? 'active' : ''}
                  onClick={() => setRangeMode('all')}>{t(RANGE_LABEL.all)}</button>
        )}
        <button type="button" className={isToday ? 'active' : ''}
                onClick={() => f.patchParams({ okres: 'custom', od: today, do: today, data: '' })}>
          {t('todayBtn')}
        </button>
        {(['week', 'month'] as RangeMode[]).map(m => (
          <button key={m} type="button" className={rangeMode === m ? 'active' : ''}
                  // klik = bieżący tydzień/miesiąc (kotwica „dziś" nie trafia do URL)
                  onClick={() => f.patchParams({ okres: m, data: '' })}>
            {t(RANGE_LABEL[m])}
          </button>
        ))}
        <button type="button" className={rangeMode === 'custom' && !isToday ? 'active' : ''}
                onClick={() => setRangeMode('custom')}>{t(RANGE_LABEL.custom)}</button>
      </div>
      {/* decyzja 13 — ‹ etykieta › tej samej linii co segmenty, tylko dla trybów z kotwicą */}
      {(rangeMode === 'month' || rangeMode === 'week') && (
        // „‹ Tydz ›": w trybie tygodnia etykietą jest wybór tygodnia (daty w tooltipie)
        <div className="range-stepper" title={rangeLabel}>
          <button type="button" className="step" title={t('prevRange')} aria-label={t('prevRange')}
                  onClick={() => step(-1)}>‹</button>
          {rangeMode === 'week' ? (
            <select className="week-pick" value={currentWeek} aria-label={t('pickWeek')}
                    onChange={e => setAnchor(isoWeekMonday(anchorYear, Number(e.target.value)))}
                    title={`${t('pickWeek')}: ${rangeLabel}`}>
              {Array.from({ length: isoWeeksInYear(anchorYear) }, (_, i) => i + 1).map(w => (
                <option key={w} value={w}>{t('weekShort')} {w}</option>
              ))}
            </select>
          ) : <span className="range-label">{rangeLabel}</span>}
          <button type="button" className="step" title={t('nextRange')} aria-label={t('nextRange')}
                  onClick={() => step(1)}>›</button>
        </div>
      )}
      <button type="button"
              className={`btn small ${rangeMode === 'fromToday' ? '' : 'secondary'}`}
              onClick={() => setRangeMode('fromToday')}>
        {t('rangeFromToday')}
      </button>
      {rangeMode === 'custom' && (
        <span className="range-stepper">
          <label>{t('dateFrom')}{' '}
            <input type="date" value={f.dateFrom} onChange={e => f.setDateFrom(e.target.value)} />
          </label>
          <label>{t('dateTo')}{' '}
            <input type="date" value={f.dateTo} onChange={e => f.setDateTo(e.target.value)} />
          </label>
        </span>
      )}
    </>
  )
}
