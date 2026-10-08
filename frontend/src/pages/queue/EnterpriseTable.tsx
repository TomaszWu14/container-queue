import { ArrowDownIcon, ArrowUpIcon, ChevronDownIcon, ChevronRightIcon, FlagIcon, TriangleAlertIcon } from 'lucide-react'
// Kolejka Enterprise: tabela 12 kolumn (kolejność i szerokości z makiety), jednolinijkowe
// wiersze 28px (Kompaktowy) / 38px (Komfortowy); kolumna 48px = checkbox + ☆/★, ● opóźnienia
// przy numerze, kolumny puste w całej tabeli ukryte (UX-022), sort po nagłówku, grupy.
import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { CustomsBadge } from '../../components'
import { formatDate, todayISO } from '../../dates'
import { useT } from '../../i18n'
import type { Container } from '../../types'
import { etaShiftDays } from '../queueRows'
import type { Cumulative } from '../queueSummary'
import { NO_WAREHOUSE, warehouseKey } from '../queueSummary'
import { idLabel, MultiCell } from './cells'
import { CopyButton } from '../../clipboard'
import { TransportBadge } from '../../TransportBadge'
import type { GroupBy, SortKey } from './config'
import { applyOrder, COMPACT_HIDDEN, DEFAULT_ORDER, emptyColumns, LOCKED_COLUMN } from './columns'
import { useHeaderDrag } from './useHeaderDrag'
import { demurrageDaysLeft, demurrageLabel, DEMURRAGE_SOON_DAYS, stageName } from './enterprise'
import type { RowGroup } from './enterprise'
import GroupBody from './EnterpriseGroup'
import WatchReasonTag from '../watch/WatchReasonTag'
import type { TileMenusState } from './TileMenus'
import type { QueueMove } from './useQueueMove'
import HeaderFilter from './columnFilter/HeaderFilter'
import type { ColFilterCtx } from './columnFilter/HeaderFilter'
import { FILTER_COLS } from './columnFilter/values'
import { MiniDocTiles } from './docTiles'
import type { DocTilesMap } from './docTiles'

export interface TableCtx {
  groups: RowGroup[]
  groupBy: GroupBy
  collapsed: Set<string>
  toggleGroup: (key: string, open: boolean) => void
  opened?: ReadonlySet<string>   // dni otwarte strzałką mimo globalnie zwiniętej sekcji planowania
  mv: QueueMove
  menus: TileMenusState
  selectable: boolean
  canEdit: boolean
  archive: boolean
  showCompany: boolean
  compact: boolean   // otwarta szuflada: bez kolumn niskiego priorytetu (Spedytor, Wypełn.)
  columns: Set<string>   // widoczne kolumny (wybór kolumn)
  colOrder?: readonly string[]   // kolejność kolumn z profilu (brak = kolejność z kodu)
  moveCol?: (key: string, target: string, after: boolean) => void   // przeciąganie nagłówka
  dense: boolean         // gęstość: wiersz 30px zamiast 38px
  fillMap: Record<number, number | null>
  docTiles?: DocTilesMap
  conflictIcon: (c: Container) => ReactNode
  expandedId: number | null
  collapseDetail: () => void
  drawerId: number | null
  openDrawer: (id: number) => void
  setStatusFor: (c: Container) => void
  watched: Set<number>
  watchReasons?: ReadonlyMap<number, string>   // powód przy ★ (etykieta w kolumnie Nr)
  toggleWatch: (id: number) => void
  sortBy: SortKey[]
  toggleSort: (key: string, additive: boolean) => void
  sortItems: (items: Container[]) => Container[]
  openCells: Set<string>
  toggleCell: (key: string) => void
  openCols?: Set<string>                  // kolumny rozwinięte strzałką w nagłówku
  toggleColOpen?: (col: string) => void
  warehouseKeys: string[]
  limitFor: (wh: string, day: string | null) => number | null
  cumByDay: Map<string, Cumulative>
  collapsedPlanning: string[]
  togglePlanSection: (status: string, groupKey?: string) => void
  onHiddenCols?: (labels: string[]) => void   // nazwy ukrytych pustych kolumn (stopka kolejki)
  colFilter?: ColFilterCtx   // lejki „jak w Excelu" w nagłówkach (brak = bez filtrów kolumn)
}

// empty: komórka bez wartości — kolumna pusta w całej widocznej tabeli nie jest renderowana
export type Col = {
  key: string; label: string; w: number; sort?: string; cell: (c: Container) => ReactNode
  empty?: (c: Container) => boolean
  multi?: boolean   // wiele numerów w komórce: licznik „› N” + „rozwiń wszystkie” w nagłówku
}
/** Szerokość kolumny wyboru: checkbox + ☆/★ (obserwuj). */
export const SEL_W = 48


function Fill({ pct }: { pct: number | null | undefined }) {
  if (pct == null) return <span className="kq-dim">—</span>
  return (
    <span className="kq-fill">
      <s><i style={{ width: `${Math.min(pct, 100)}%` }} className={pct >= 90 ? 'full' : ''} /></s>
      <small className="mono">{Math.round(pct)}%</small>
    </span>
  )
}

export default function EnterpriseTable({ x }: { x: TableCtx }) {
  const t = useT()
  const navigate = useNavigate()
  const today = todayISO()
  const { mv } = x
  // komórka wielu numerów: otwarta = kolumna rozwinięta w nagłówku XOR własny klik;
  // zaznaczone w filtrze kolumny wartości idą na wierzch zwiniętej komórki
  const multi = (c: Container, col: string, raw: string | null) => {
    const flt = x.colFilter?.filters[col]
    return <MultiCell raw={raw} copyable hits={flt && 'in' in flt ? flt.in : undefined}
                      open={(x.openCols?.has(col) ?? false) !== x.openCells.has(`${c.id}:${col}`)}
                      onToggle={() => x.toggleCell(`${c.id}:${col}`)} />
  }
  const allCols: Col[] = [
    { key: 'no', label: t('containerNo'), w: 124, sort: 'containerNo', cell: c => (
      <span className="kq-no">
        {/* ● opóźnienia (6px, czerwona) przed numerem */}
        {c.is_delayed && <i className="kq-late-dot" role="img" title={t('delayed')} aria-label={t('delayed')} />}
        <b className="mono">{idLabel(c)}</b>
        {c.container_no && <CopyButton text={c.container_no} />}
        {c.customer_order && <span title={`${t('customerOrderFlag')}: ${c.customer_order}`}><FlagIcon size={14} /></span>}
        {x.conflictIcon(c)}
        {c.is_stuck && <span className="kq-stuck" title={t('stuckHint')}>⏸</span>}
        {x.watched.has(c.id) && <WatchReasonTag reason={x.watchReasons?.get(c.id) ?? ''} />}
      </span>) },
    ...(x.showCompany ? [{ key: 'company', label: t('company'), w: 100, cell: (c: Container) => c.company_name }] : []),
    { key: 'supplier', label: t('supplier'), w: 112, sort: 'supplier', empty: c => !c.supplier_name, cell: c => (
      <span className={`kq-sup${c.supplier_id ? ' link-like' : ''}`}
            title={c.supplier_id || !c.supplier_name ? c.supplier_name ?? undefined : t('supRawHint')}
            onClick={e => { e.stopPropagation(); if (c.supplier_id) navigate(`/dostawcy/${c.supplier_id}`) }}>
        {c.supplier_name || '—'}
      </span>) },
    { key: 'vessel', label: t('vessel'), w: 112, sort: 'vessel', empty: c => !c.vessel,
      cell: c => <span title={c.vessel}>{c.vessel || '—'}</span> },
    { key: 'eta', label: t('eta'), w: 112, sort: 'eta', empty: c => !(c.atd ?? c.eta ?? c.eta_estimate), cell: c => {
      const shift = etaShiftDays(c)
      const v = c.atd ?? c.eta ?? c.eta_estimate
      return (
        <span className={`mono kq-dim${shift ? ' kq-shift' : ''}`}
              title={shift ? t('planEtaShift').replace('{days}', String(shift)) : formatDate(v)}>
          {formatDate(v, !c.atd && !c.eta && !!c.eta_estimate)}{shift && <> <TriangleAlertIcon size={12} /></>}
        </span>)
    } },
    { key: 'notify', label: t('kqColDelivery'), w: 136, sort: 'notifyDate', empty: c => !c.notify_date, cell: c => (
      <span className={`mono${c.is_delayed ? ' kq-late' : ''}`}
            title={c.planning_status === 'WYSLANE' && c.planning_sent_at
              ? t('planSentAt').replace('{date}', formatDate(c.planning_sent_at)) : formatDate(c.notify_date)}>
        {formatDate(c.notify_date)}{c.slot_time ? ` ${c.slot_time}` : ''}
      </span>) },
    // grupowanie po etapie = etap jest w nagłówku grupy → bez kolumny Status; w innych
    // grupowaniach zwykły tekst 12px (kolor etapu niesie pasek 3px przy lewej krawędzi)
    ...(x.groupBy === 'status' ? [] : [{ key: 'status', label: t('status'), w: 150, sort: 'status', cell: (c: Container) => {
      // bez prefiksu numeru etapu („4 · ") — pełna nazwa w title
      const full = t(`st_${c.status}`)
      return <span className="kq-st" title={full}>{stageName(full)}</span>
    } }]),
    { key: 'customs', label: t('customs'), w: 124, sort: 'customs', empty: c => c.customs_status === 'BRAK', cell: c =>
      // „Brak" odprawy = szary „—" zamiast badge'a
      c.customs_status === 'BRAK' ? <span className="kq-none" title={t('cs_BRAK')}>—</span>
        : <CustomsBadge status={c.customs_status} /> },
    { key: 'wh', label: t('warehouse'), w: 98, sort: 'warehouse',
      empty: c => warehouseKey(c.warehouse_name) === NO_WAREHOUSE, cell: c =>
      warehouseKey(c.warehouse_name) === NO_WAREHOUSE
        ? <span className="kq-none">—</span> : <b className="kq-wh">{c.warehouse_name}</b> },
    { key: 'fwd', label: t('forwarder'), w: 82, sort: 'forwarder', empty: c => !c.forwarder_name,
      cell: c => c.forwarder_name || '—' },
    { key: 'order', label: t('kqColOrder'), w: 190, sort: 'orderNumbers', multi: true,
      empty: c => !(c.order_numbers || c.order_number), cell: c => multi(c, 'order', c.order_numbers || c.order_number) },
    { key: 'dem', label: t('kqColDemurrage'), w: 96, sort: 'demurrage',
      empty: c => demurrageDaysLeft(c, today) === null, cell: c => {
      const left = demurrageDaysLeft(c, today)
      if (left === null) return <span className="kq-dim">—</span>
      const tone = left <= 0 ? 'over' : left <= DEMURRAGE_SOON_DAYS ? 'soon' : ''
      return <span className={`kq-dem mono ${tone}`} title={formatDate(c.demurrage_deadline ?? null)}>
        {demurrageLabel(left, t('kqDaysLeft'))}</span>
    } },
    { key: 'fill', label: t('kqColFill'), w: 72, empty: c => x.fillMap[c.id] == null,
      cell: c => <Fill pct={x.fillMap[c.id]} /> },
    { key: 'docs', label: t('kqColDocs'), w: 150, empty: c => !x.docTiles?.[c.id], cell: c => {
      const d = x.docTiles?.[c.id]
      return d ? <MiniDocTiles d={d} /> : null
    } },
    // opcjonalne pola z dawnej kolejki (wybór kolumn) — domyślnie ukryte
    { key: 'etd', label: t('etdCol'), w: 100, empty: c => !c.etd,
      cell: c => <span className="mono kq-dim" title={formatDate(c.etd)}>{formatDate(c.etd)}</span> },
    { key: 'transport', label: t('transport'), w: 108, empty: c => !c.transport_type, cell: c =>
      c.transport_type ? <TransportBadge type={c.transport_type} /> : '—' },
    { key: 'onCarriage', label: t('onCarriage'), w: 116, empty: c => !c.on_carriage, cell: c =>
      c.on_carriage ? <TransportBadge type={c.on_carriage} /> : '—' },
    { key: 'deliveryNote', label: t('kqColDeliveryNote'), w: 120, empty: c => !c.delivery_note,
      cell: c => <span title={c.delivery_note}>{c.delivery_note || '—'}</span> },
    { key: 'incomingNo', label: t('incomingDeliveryNo'), w: 190, multi: true, empty: c => !c.incoming_delivery_no,
      cell: c => multi(c, 'incomingNo', c.incoming_delivery_no) },
    { key: 'purchaseNote', label: t('purchaseNote'), w: 110, empty: c => !c.purchase_note,
      cell: c => <span title={c.purchase_note}>{c.purchase_note || '—'}</span> },
    { key: 'docFlow', label: t('documentFlow'), w: 110, empty: c => !c.document_flow,
      cell: c => <span title={c.document_flow}>{c.document_flow || '—'}</span> },
    { key: 'sentReq', label: t('kqColSentReq'), w: 88, empty: c => c.sent_required == null, cell: c =>
      c.sent_required == null ? '—' : t(c.sent_required ? 'yes' : 'no') },
    { key: 'sentNo', label: t('sentNoCol'), w: 104, empty: c => !c.sent_number,
      cell: c => <span className="mono">{c.sent_number || '—'}</span> },
    { key: 'sentStatus', label: t('kqColSentStatus'), w: 100, empty: c => !c.sent_status,
      cell: c => c.sent_status || '—' },
  ]
  // widoczne = wybór użytkownika (kolumna spółki poza wyborem — tylko we wspólnym fallbacku);
  // otwarta szuflada dodatkowo chowa kolumny niskiego priorytetu
  // kolejność z profilu; kolumny spoza zapisu (spółka, nowe w kodzie) na swoim domyślnym miejscu
  const rank = new Map(applyOrder(allCols.map(col => col.key), x.colOrder ?? null).map((k, i) => [k, i]))
  const shown = [...allCols].sort((a, b) => rank.get(a.key)! - rank.get(b.key)!)
    .filter(col => (col.key === 'company' || x.columns.has(col.key)) && !(x.compact && COMPACT_HIDDEN.has(col.key)))
  // kolumny puste w całej widocznej tabeli znikają (UX-022: 4–6 kolumn z nagłówkiem „—" nic nie
  // mówiło i zabierało szerokość); ich nazwy pokazuje stopka kolejki
  // (liczone przed filtrami kolumn — filtr „(Puste)" nie może schować własnego lejka)
  const empty = emptyColumns(shown, x.colFilter?.rows ?? x.groups.flatMap(g => g.items))
  const cols = shown.filter(col => !empty.has(col.key))
  const hidden = shown.filter(col => empty.has(col.key)).map(col => col.label)
  const hiddenKey = hidden.join('\u0000')
  const onHidden = x.onHiddenCols
  useEffect(() => { onHidden?.(hiddenKey ? hiddenKey.split('\u0000') : []) }, [hiddenKey, onHidden])
  const span = cols.length + 2
  // szerokość minimalna = suma kolumn (fixed layout) — węższa tabela przy otwartej szufladzie
  const minWidth = cols.reduce((n, col) => n + col.w, SEL_W + 36)
  const flexW = cols.reduce((n, col) => n + col.w, 0)
  const drag = useHeaderDrag(x.moveCol)
  const sortMark = (key?: string) => {
    const i = x.sortBy.findIndex(s => s.key === key)
    if (i < 0) return null
    return <span className="kq-sort">{x.sortBy[i].dir === 1 ? <ArrowUpIcon size={12} /> : <ArrowDownIcon size={12} />}{x.sortBy.length > 1 ? i + 1 : ''}</span>
  }
  return (
    <div className="kq-scroll">
      <table className={`kq-table${x.dense ? ' dense' : ''}`} style={{ minWidth }}>
        <colgroup>
          <col style={{ width: SEL_W }} />
          {/* kolumny danych w % — nadmiar szerokości rozkłada się proporcjonalnie */}
          {cols.map(col => <col key={col.key} style={{ width: `${(col.w / flexW) * 100}%` }} />)}
          <col style={{ width: 36 }} />
        </colgroup>
        <thead>
          <tr>
            <th className="kq-sel">
              {!x.selectable && <span className="sr-only">{t('kqFlag')}</span>}
              {x.selectable && <input type="checkbox" aria-label={t('selectAll')}
                checked={mv.allSelected} onChange={mv.toggleSelectAll} />}
            </th>
            {cols.map(col => (
              <th key={col.key} {...drag.thProps(col.key, col.key !== LOCKED_COLUMN && DEFAULT_ORDER.includes(col.key))}
                  className={`kq-h-${col.key}${col.sort ? ' sortable' : ''}${x.sortBy.some(s => s.key === col.sort) ? ' sorted' : ''}${drag.dropClass(col.key)}`}
                  aria-sort={col.sort && x.sortBy[0]?.key === col.sort ? (x.sortBy[0].dir === 1 ? 'ascending' : 'descending') : undefined}
                  onClick={e => col.sort && x.toggleSort(col.sort, e.shiftKey)}>
                {/* lejek przed etykietą (float: right) — przy wąskiej kolumnie ucina się etykieta, nie lejek */}
                {x.colFilter && FILTER_COLS[col.key] && <HeaderFilter col={col.key} label={col.label} ctx={x.colFilter} />}
                {col.multi && x.toggleColOpen && (
                  <button type="button" className="kq-h-expand" aria-pressed={x.openCols?.has(col.key) ?? false}
                          title={t(x.openCols?.has(col.key) ? 'collapseAllValues' : 'expandAllValues')}
                          aria-label={`${t(x.openCols?.has(col.key) ? 'collapseAllValues' : 'expandAllValues')}: ${col.label}`}
                          onClick={e => { e.stopPropagation(); x.toggleColOpen?.(col.key) }}>
                    {x.openCols?.has(col.key) ? <ChevronDownIcon size={12} aria-hidden="true" />
                      : <ChevronRightIcon size={12} aria-hidden="true" />}
                  </button>
                )}
                {col.label}{sortMark(col.sort)}
              </th>
            ))}
            <th className="kq-more"><span className="sr-only">{t('moreActions')}</span></th>
          </tr>
        </thead>
        {x.groups.map(g => (
          <GroupBody key={g.key || 'none'} g={g} x={x} cols={cols} span={span} />
        ))}
      </table>
    </div>
  )
}
