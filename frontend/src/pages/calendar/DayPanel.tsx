// Panel wybranego dnia: nagłówek, KPI dnia i lista awizacji per magazyn (slot, kontener,
// statek · spedytor, status odprawy); opóźnione wyróżnione.
import { useContext } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUser } from '../../App'
import { seesCustoms } from '../../routing'
import { formatDate, formatDayLong, isoWeek } from '../../dates'
import { LangContext, localeFor, useT } from '../../i18n'
import type { QueueDay } from '../../types'
import { type DayStat, whName } from './calModel'

const CUSTOMS_TONE: Record<string, string> = {
  ODPRAWIONY: 'ok', ZWOLNIONY: 'ok', ROZLICZONY: 'ok', ZLECONA: 'warn', DRAFT_WYSLANY: 'warn',
  DRAFT_POTWIERDZONY: 'warn', REWIZJA: 'bad',
}

export default function DayPanel({ iso, info, s, holiday }: {
  iso: string; info: QueueDay | undefined; s: DayStat; holiday: string | null
}) {
  const t = useT()
  const { lang } = useContext(LangContext)
  const navigate = useNavigate()
  const showCustoms = seesCustoms(useUser()?.role)
  const title = formatDayLong(iso, localeFor(lang))
  const items = [...(info?.containers ?? [])].sort((a, b) => (a.slot_time || '99').localeCompare(b.slot_time || '99'))
  const openDay = () => navigate(`/kolejka?okres=custom&od=${iso}&do=${iso}`)
  return (
    <aside className="panel cal2-panel">
      <div className="cal2-p-head">
        <div className="mono muted">{formatDate(iso)} · T{isoWeek(iso)}</div>
        <h2>{title}</h2>
        {s.closed ? <span className="cal2-chip">{holiday ?? t('calClosedWh')}</span>
          : <span className="cal2-chip free">{t('calFreeSlots')}: {s.free}</span>}
      </div>
      {!s.closed && (
        <div className="cal2-p-kpis">
          <div><small>{t('calBookings')}</small><b className="mono">{s.total}/{s.cap}</b></div>
          <div><small>{t('calPanelFree')}</small><b className="mono ok">{s.free}</b></div>
          <div><small>{t('calPanelLate')}</small><b className="mono bad">{s.late}</b></div>
          {showCustoms && <div><small>{t('calPanelCustoms')}</small><b className="mono warn">{s.customsOpen}</b></div>}
        </div>
      )}
      <div className="cal2-p-list">
        {s.byWh.map(w => {
          const rows = items.filter(c => whName(c) === w.key)
          return (
            <section key={w.key}>
              <div className="cal2-p-wh">
                <b>{w.key}</b>
                <span className={`cal2-p-bar wh-${w.key.toLowerCase()}`}>
                  <i style={{ width: `${w.limit ? Math.min(100, (w.n / w.limit) * 100) : 0}%` }} />
                </span>
                <span className="mono muted">{w.n}/{w.limit}</span>
              </div>
              {rows.map(c => (
                <div key={c.id} className={`cal2-p-row${c.is_delayed ? ' late' : ''}`}
                     role="button" tabIndex={0} onClick={() => navigate(`/kontenery/${c.id}`)}
                     onKeyDown={e => { if (e.key === 'Enter') navigate(`/kontenery/${c.id}`) }}>
                  {/* A23: pusta godzina slotu bez „—” (wyglądało jak brak danych kontenera) */}
                  <span className="mono cal2-p-time">{c.slot_time || ''}</span>
                  <span className="cal2-p-main">
                    <b className="mono">{c.container_no}</b>
                    <span className={`badge st-${c.status}`}>{t(`st_${c.status}`)}</span>
                    <small className="muted">{[c.supplier_name, c.vessel, c.forwarder_name].filter(Boolean).join(' · ')}</small>
                    {c.is_delayed && <small className="bad">{t('calLateRow')}</small>}
                  </span>
                  {showCustoms && (
                    <span className={`cal2-cs ${CUSTOMS_TONE[c.customs_status] ?? ''}`}>
                      {t('customs')}: {t(`cs_${c.customs_status}`).toLowerCase()}
                    </span>)}
                </div>
              ))}
            </section>
          )
        })}
      </div>
      <div className="cal2-p-actions">
        <button className="btn secondary" onClick={openDay}>{t('calMoveBooking')}</button>
        <button className="btn" onClick={openDay}>{t('calOpenDay')}</button>
      </div>
    </aside>
  )
}
