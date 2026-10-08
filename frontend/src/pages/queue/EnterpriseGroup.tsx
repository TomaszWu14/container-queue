// Kolejka Enterprise: grupa tabeli — nagłówek w jednej linii ≤28px (sticky pod nagłówkiem kolumn),
// sekcje planowania (Potwierdzone / Wysłane / Propozycje — zwijane, pamiętane): przy jednej sekcji
// tylko licznik w nagłówku grupy, przy 2–3 cienkie separatory 22px. Drop w trybie edycji
// przenosi na dzień grupy.
import { Fragment, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import { HelpTip } from '../../HelpTip'
import { parseISO, todayISO } from '../../dates'
import { LangContext, localeFor, useT } from '../../i18n'
import type { Container } from '../../types'
import ContainerDetailPanel from '../ContainerDetailPanel'
import { splitByPlanning } from '../queueRows'
import { bandWarehouses, NO_WAREHOUSE, warehouseKey } from '../queueSummary'
import { CONTAINER_STATUSES } from '../../types'
import { stageName } from './enterprise'
import type { RowGroup } from './enterprise'
import type { Col, TableCtx } from './EnterpriseTable'
import { ChevronDownIcon, ChevronRightIcon, Ellipsis, StarIcon } from 'lucide-react'

// kolor dnia tygodnia (nd..sb) — kwadracik w nagłówku grupy (makieta)
const DAY_COLORS = ['#F3ABA2', '#A9D2EE', '#A0D8D0', '#C2B6DF', '#F4C59B', '#F5AAC5', '#C1D4A9']
const WH_COLORS: Record<string, string> = { ACME: 'var(--wh-acme)', DLT: 'var(--wh-dlt)' }
// tło wiersza wg magazynu — ten sam klucz co kolumna Magazyn / grupa „Magazyn"; kolor tylko DLT i ACME
const rowWarehouseClass = (name: string | null) => {
  const k = warehouseKey(name)
  return k === 'DLT' || k === 'ACME' ? ` kq-wh-${k.toLowerCase()}` : ''
}
const PLAN_KEYS: Record<string, [string, string]> = {
  POTWIERDZONE: ['planConfirmed', 'helpPlanConfirmed'],
  WYSLANE: ['planSent', 'helpPlanSent'],
  PROPOZYCJA: ['planProposal', 'helpPlanProposal'],
}

export default function GroupBody({ g, x, cols, span }: { g: RowGroup; x: TableCtx; cols: Col[]; span: number }) {
  const t = useT()
  const { lang } = useContext(LangContext)
  const { mv } = x
  const [hover, setHover] = useState(false)
  const isDay = x.groupBy === 'weekday'
  // sekcja zwinięta globalnie, chyba że dzień otwarto ręcznie strzałką (useGroupCollapse)
  const isShut = (status: string) => x.collapsedPlanning.includes(status) && !x.opened?.has(g.key)
  const dropOk = mv.moveActive && isDay && !!g.key

  let title: ReactNode = g.key, sub = '', color = '#c1c9d4'
  if (isDay) {
    if (g.key) {
      const d = parseISO(g.key)
      title = new Intl.DateTimeFormat(localeFor(lang), { day: 'numeric', month: 'long', timeZone: 'UTC' }).format(d)
      sub = new Intl.DateTimeFormat(localeFor(lang), { weekday: 'long', timeZone: 'UTC' }).format(d)
      color = DAY_COLORS[d.getUTCDay()]
    } else title = t('noNotifyDate')
  } else if (x.groupBy === 'status') {
    title = t(`st_${g.key}`)
    sub = t('kqStageSub').replace('{n}', String(CONTAINER_STATUSES.indexOf(g.key as never) + 1))
      .replace('{m}', String(CONTAINER_STATUSES.length))
    color = '#b9d0f0'
  } else {
    title = g.key === NO_WAREHOUSE ? t('noWarehouse') : g.key
    sub = t('kqWhSub')
    color = WH_COLORS[g.key] ?? color
  }
  // limity dzienne magazynów tylko w grupowaniu po dniu (limit jest per dzień)
  const limits = isDay && g.key
    ? bandWarehouses(g.items, x.warehouseKeys)
      .map(w => ({ ...w, limit: w.key === NO_WAREHOUSE ? null : x.limitFor(w.key, g.key) }))
      .filter(w => w.limit != null)
    : []
  const cum = isDay && g.key ? x.cumByDay.get(g.key) : undefined
  const sections = splitByPlanning(g.items)
  const single = sections.length === 1
  // strzałka = czy grupa pokazuje teraz jakiekolwiek wiersze
  const open = !x.collapsed.has(g.key) && sections.some(s => !isShut(s.status))
  const planBtn = (status: string, n: number, cls: string) => {
    const shut = isShut(status)
    return (
      <button type="button" className={cls} aria-expanded={!shut} title={t(PLAN_KEYS[status][1])}
              onClick={() => x.togglePlanSection(status, g.key)}>
        {shut && <ChevronRightIcon size={14} />}{t(PLAN_KEYS[status][0])} <span className="mono">({n})</span>
      </button>
    )
  }

  return (
    <tbody className={`kq-group${hover && dropOk ? ' drop-target' : ''}`}
           onDragOver={e => { if (!dropOk) return; e.preventDefault(); setHover(true) }}
           onDragLeave={() => setHover(false)}
           onDrop={e => { setHover(false); mv.handleDrop(e, g.key) }}>
      <tr className={`kq-ghead${g.key === todayISO() ? ' today' : ''}`}>
        <td colSpan={span}>
          <div className="kq-ghead-in">
            <button type="button" className="kq-caret" aria-expanded={open} title={t('kqToggleGroup')}
                    aria-label={t('kqToggleGroup')} onClick={() => x.toggleGroup(g.key, open)}>{open ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}</button>
            {x.selectable && (
              <input type="checkbox" title={t('selectDay')} aria-label={t('selectDay')}
                     checked={g.items.every(c => mv.selected.has(c.id))}
                     onChange={() => mv.toggleSelectDay(g.items)} />
            )}
            <i className="kq-sq" style={{ background: color }} aria-hidden="true" />
            <b className="kq-gtitle">{title}</b>
            {sub && <span className="kq-gsub">· {sub}</span>}
            <span className="kq-gchip">{t('kqContShort').replace('{n}', String(g.items.length))}</span>
            {limits.map(w => (
              <span key={w.key} className={`kq-gchip mono${w.n > w.limit! ? ' warn' : ''}`}>
                {w.key} {w.n}/{w.limit}
              </span>
            ))}
            {cum && (
              // suma narastająca od poniedziałku (Σ), w tooltipie rozbicie per magazyn
              <span className="kq-gchip mono" title={`${t('cumHint')}: ${Object.entries(cum.byWh)
                .map(([k, n]) => `${k === NO_WAREHOUSE ? t('noWarehouse') : k} ${n}`).join(' · ')}`}>
                Σ {cum.total}
              </span>
            )}
            {/* jedna sekcja planowania → sam licznik w nagłówku (nadal zwija sekcję) */}
            {single && <>· {planBtn(sections[0].status, sections[0].items.length,
              `kq-gplan plan-${sections[0].status.toLowerCase()}`)}</>}
          </div>
        </td>
      </tr>
      {!x.collapsed.has(g.key) && sections.map(({ status, items }) => {
        const shut = isShut(status)
        const [label, help] = PLAN_KEYS[status]
        return (
          <Fragment key={status}>
            {!single && (
              <tr className={`kq-plan plan-${status.toLowerCase()}`}>
                <td colSpan={span}>
                  {planBtn(status, items.length, 'kq-plan-btn')}
                  <HelpTip label={`${t('helpLabel')}: ${t(label)}`} text={t(help)} />
                </td>
              </tr>
            )}
            {!shut && x.sortItems(items).map(c => <Row key={c.id} c={c} x={x} cols={cols} span={span} />)}
          </Fragment>
        )
      })}
    </tbody>
  )
}

function Row({ c, x, cols, span }: { c: Container; x: TableCtx; cols: Col[]; span: number }) {
  const t = useT()
  const { mv } = x
  const expanded = x.expandedId === c.id
  const sel = mv.selected.has(c.id)
  const watched = x.watched.has(c.id)
  return (
    <Fragment>
      <tr data-cid={c.id}
          className={`kq-row stg-${c.status}${rowWarehouseClass(c.warehouse_name)}${sel ? ' selected' : ''}${expanded || x.drawerId === c.id ? ' active' : ''}${mv.dragId === c.id ? ' dragging' : ''}`}
          draggable={mv.moveActive}
          onClick={e => {
            if ((e.target as HTMLElement).closest('input,button,select,a,.link-like')) return
            if (expanded) { x.collapseDetail(); return }   // klik w rozwinięty wiersz zwija panel
            x.openDrawer(c.id)   // klik w wiersz = szuflada; pełny panel pod „Pełna karta"
          }}
          onContextMenu={e => {
            // prawy przycisk → kalendarz zmiany daty awizacji
            if (!x.canEdit || x.archive) return
            e.preventDefault()
            x.menus.setWhMenu(null)
            x.menus.setDateMenu({ c, x: e.clientX, y: e.clientY })
          }}
          onDragStart={e => {
            const ids = sel ? [...mv.selected] : [c.id]
            if (!sel) mv.setSelected(new Set([c.id]))
            e.dataTransfer.setData('text/plain', ids.join(','))
            e.dataTransfer.effectAllowed = 'move'
            mv.setDragId(c.id)
          }}
          onDragEnd={() => { mv.setDragId(null); mv.setDropDay(null) }}>
        {/* A16: kolorowy pasek przy lewej krawędzi = etap — nazwa w podpowiedzi */}
        <td className="kq-sel" title={t('kqStageBar').replace('{stage}', stageName(t(`st_${c.status}`)))}>
          {x.selectable && (
            <input type="checkbox" checked={sel} aria-label={t('kqSelectRow')} onChange={() => mv.toggleSelect(c.id)} />
          )}
          {/* ☆/★ obserwuj — klik przełącza obserwowanie (dodanie pyta o powód) */}
          {/* pełna gwiazdka: podpowiedź = powód obserwacji (2026-09-30), akcja zostaje w aria-label */}
          <button type="button" className={`kq-flag-btn${watched ? ' star' : ''}`}
                  title={watched ? (x.watchReasons?.get(c.id) || t('watchingNoReason')) : t('watchToggle')}
                  aria-label={watched
                    ? `${t('watchToggle')} — ${x.watchReasons?.get(c.id) || t('watchingNoReason')}`
                    : t('watchToggle')}
                  aria-pressed={watched}
                  onClick={() => x.toggleWatch(c.id)}>
            <StarIcon size={14} fill={watched ? 'currentColor' : 'none'} />
          </button>
        </td>
        {/* data-label: podpis pola, gdy na telefonie wiersz jest kartą (CSS) */}
        {cols.map(col => <td key={col.key} data-label={col.label} className={`kq-c-${col.key}`}>{col.cell(c)}</td>)}
        <td className="kq-more">
          <button type="button" className="kq-more-btn" aria-label={t('moreActions')} title={t('moreActions')}
                  onClick={e => {
                    e.stopPropagation()  // inaczej ten sam klik dociera do window i useDismiss od razu zamyka menu
                    const r = e.currentTarget.getBoundingClientRect()
                    x.menus.setWhMenu(null); x.menus.setDateMenu(null)
                    x.menus.setTileMenu({ c, x: r.right, y: r.bottom + 4 })
                  }}><Ellipsis size={16} aria-hidden="true" /></button>
        </td>
      </tr>
      {expanded && (
        <tr className="kq-detail"><td colSpan={span}>
          <ContainerDetailPanel container={c} onOpenStatus={x.setStatusFor} onClose={x.collapseDetail} />
        </td></tr>
      )}
    </Fragment>
  )
}
