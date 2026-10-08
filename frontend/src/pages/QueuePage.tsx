import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUser } from '../App'
import { resolveModule } from '../urlState'
import { api, errorMessage } from '../api'
import { totalOf } from '../listTotal'
import { ChartColumnIcon, Inbox, SearchX } from 'lucide-react'
import { EmptyState, LoadError, Skeleton, useToast } from '../feedback'
import { HelpTip } from '../HelpTip'
import { ContainerFormModal, StatusModal, useDicts } from '../components'
import { todayISO } from '../dates'
import { useT } from '../i18n'
import type { Company, Container, Supplier } from '../types'
import { CONTAINER_STATUSES, CUSTOMS_STATUSES } from '../types'
import { cumulativeByDay, summarizeRange } from './queueSummary'
import { groupByWeek } from './queueRows'
import { useFillSummary } from './queueFill'
import { useDocTiles } from './queue/docTiles'
import AnalysisTab from './AnalysisTab'
import AvizoSendModal from './AvizoSendModal'
import ClearQueueModal from './ClearQueueModal'
import QuoteRequestModal from './QuoteRequestModal'
import FoundOrderModal from './FoundOrderModal'
import PurchaseOrdersPanel from './PurchaseOrdersPanel'
import { MonthlyZipBar } from '../DocumentsW5'
// Kolejka rozbita na moduły w ./queue/ (≤500 linii/plik): stałe, komórki, hooki
// filtrów/preferencji/przenoszenia/sygnałów, pasek narzędzi, Kolejka Enterprise (KPI+tabela), menu.
import { MODULE_CODE, MODULE_TRANSIT, MODULE_WAREHOUSE, WAREHOUSE_OPTIONS, ACME } from './queue/config'
import type { Module } from './queue/config'
import { activeFilterChips, containerQuery, useQueueFilters } from './queue/useQueueFilters'
import { useViewPrefs } from './queue/useViewPrefs'
import { ROLE_HIDDEN_COLUMNS } from './queue/columns'
import { seesCustoms } from '../routing'
import { useQueueMove } from './queue/useQueueMove'
import { useSearchFocus } from './queue/useSearchFocus'
import { useGroupCollapse } from './queue/useGroupCollapse'
import { useTransportConflicts, useUrgency } from './queue/useQueueSignals'
import CompanyTabs from './queue/CompanyTabs'
import QueueFilterBar, { useQueueExport } from './queue/QueueFilterBar'
import { groupContainers, matchesView, rowOrder, viewCounts } from './queue/enterprise'
import QueueDrawer from './queue/QueueDrawer'
import { useOpenFullCard, useReturnScroll } from './queue/fullCard'
import { EnterpriseFilters } from './queue/EnterpriseBar'
import EnterpriseTable from './queue/EnterpriseTable'
import TileMenus, { useTileMenus } from './queue/TileMenus'
import { MoveConfirmModal } from './queue/MoveConfirm'
import BulkActionBar from './queue/BulkActionBar'
import { applyColFilters, colFilterChips, parseColFilters, serializeColFilters, withColFilter } from './queue/columnFilter/values'
import type { ColFilter } from './queue/columnFilter/values'

const EXPANDED_KEY = 'queue.expandedId'

export default function QueuePage({ archive = false }: { archive?: boolean }) {
  const t = useT()
  const user = useUser()
  const navigate = useNavigate()
  const dicts = useDicts()
  const { showToast } = useToast()
  const [containers, setContainers] = useState<Container[]>([])
  const [companies, setCompanies] = useState<Company[]>([])
  const [companyCounts, setCompanyCounts] = useState<Record<string, number> | null>(null)
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [showAvizo, setShowAvizo] = useState(false)
  // awizacja jednego kontenera z szuflady (bez ruszania zaznaczenia)
  const [avizoOne, setAvizoOne] = useState<Container | null>(null)
  const [showQuote, setShowQuote] = useState(false)
  const [showFound, setShowFound] = useState(false)
  const [showClearQueue, setShowClearQueue] = useState(false)
  const [statusFor, setStatusFor] = useState<Container | null>(null)
  const prefs = useViewPrefs(ROLE_HIDDEN_COLUMNS[user?.role ?? ''])
  const { groupBy, sortBy, sortItems } = prefs

  const canEdit = user?.role === 'admin' || user?.role === 'logistics'
  const isAdmin = user?.role === 'admin'
  const isWarehouse = user?.role === 'warehouse'
  // admin / konto wielospółkowe widzą wszystkie zakładki; pozostali — tylko swoją spółkę
  const seesAll = isAdmin || !!user?.view_all_companies
  const ownModule = (Object.entries(MODULE_CODE) as [Module, string][])
    .find(([, code]) => code === user?.company_code)?.[0]

  // filtry i zakres dat — całość w query string (linkowalne, odświeżalne, „wstecz")
  const f = useQueueFilters(archive ? 'all' : 'week')
  const { searchParams, patchParams, queryFrom, queryTo } = f
  // Wybrana spółka w URL (?spolka=…; ?firm= = alias wstecz-kompatybilny dla starych linków).
  // Konta bez wglądu we wszystkie spółki są zablokowane na własnej — URL ich nie przełącza.
  const defaultModule: Module = seesAll ? 'acme' : (ownModule ?? 'main')
  const requestedModule = searchParams.get('spolka') || searchParams.get('firm') || ''
  const module = resolveModule(requestedModule, seesAll, defaultModule) as Module
  // domyślna spółka NIE trafia do URL (czyste params); kasujemy też legacy alias ?firm=
  const setModule = useCallback((m: Module) =>
    patchParams({ spolka: m === defaultModule ? '' : m, firm: '' }), [defaultModule, patchParams])
  const moduleCode = MODULE_CODE[module]
  const moduleWarehouse = MODULE_WAREHOUSE[module]
  const moduleTransit = MODULE_TRANSIT[module] ?? false
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  // rozwijany panel szczegółów inline (akordeon, jeden naraz) — zastąpił drawer podglądu
  // rozwinięty wiersz przeżywa F5 (sessionStorage = per karta przeglądarki)
  const [expandedId, setExpandedIdState] = useState<number | null>(() => {
    try { return Number(sessionStorage.getItem(EXPANDED_KEY)) || null } catch { return null }
  })
  const setExpandedId = (next: number | null | ((cur: number | null) => number | null)) =>
    setExpandedIdState(cur => {
      const v = typeof next === 'function' ? next(cur) : next
      try { if (v) sessionStorage.setItem(EXPANDED_KEY, String(v)); else sessionStorage.removeItem(EXPANDED_KEY) } catch { /* brak storage */ }
      return v
    })
  const [loadError, setLoadError] = useState('')
  const [total, setTotal] = useState<number | null>(null)   // X-Total-Count — lista obcięta limitem
  const warehouseOptions = WAREHOUSE_OPTIONS[module] ?? []
  const selectable = canEdit && !archive

  // wspólne parametry zapytania o kontenery — jedno źródło dla listy i eksportu;
  // tożsamość callbacku zmienia się tylko, gdy zmienia się samo zapytanie
  const queryString = containerQuery(f, archive, moduleCode, moduleWarehouse, moduleTransit).toString()
  const containerParams = useCallback(() => new URLSearchParams(queryString), [queryString])

  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null)
  const [hiddenCols, setHiddenCols] = useState<string[]>([])   // puste kolumny ukryte przez tabelę
  const loadSeq = useRef(0)
  const load = useCallback(() => {
    if (module === 'analysis') return
    setLoading(true)
    const params = containerParams()
    // straż kolejności: tylko najnowsze żądanie może nadpisać listę (bez wyścigu filtrów)
    const seq = ++loadSeq.current
    api.get<Container[]>(`/api/containers?${params}`)
      .then(data => { if (seq === loadSeq.current) { setContainers(data); setTotal(totalOf(data)); setLoadError(''); setRefreshedAt(new Date()) } })
      .catch(err => { if (seq === loadSeq.current) setLoadError(errorMessage(err)) })
      .finally(() => { if (seq === loadSeq.current) setLoading(false) })
  }, [module, containerParams])

  const replaceContainer = (saved: Container) =>
    setContainers(list => {
      const updated = list.map(c => (c.id === saved.id ? saved : c))
      return updated.some(c => c.id === saved.id) ? updated : [...updated, saved]
    })

  const { view, specialOnly } = f
  const today = todayISO()
  // filtr klienta „Specjalne" (specjalna troska) → baza KPI i liczników zakładek; zakładka
  // widoku (Opóźnione / Demurrage / Odprawa / ★ Moje) zawęża dalej. Wspólne źródło dla
  // wierszy i zaznaczania — „zaznacz wszystko" nie sięga ukrytych
  const baseContainers = useMemo(() =>
    specialOnly ? containers.filter(c => c.customer_order) : containers, [containers, specialOnly])
  // mini-kafelki dokumentów (queue/docTiles.tsx): jedno żądanie na całą listę — kolumna + zakładki
  const baseIds = useMemo(() => baseContainers.map(c => c.id), [baseContainers])
  const docTiles = useDocTiles(baseIds, module !== 'analysis' && user?.role !== 'sales')
  const viewContainers = useMemo(() =>
    baseContainers.filter(c => matchesView(c, view, today, prefs.watched, docTiles)),
  [baseContainers, view, today, prefs.watched, docTiles])
  // filtry w nagłówkach kolumn „jak w Excelu" — po stronie klienta, AND z resztą (URL ?kolumny=)
  const { colFiltersRaw, setColFiltersRaw } = f
  const colFilters = useMemo(() => parseColFilters(colFiltersRaw), [colFiltersRaw])
  const setColFilter = useCallback((col: string, v: ColFilter | null) =>
    setColFiltersRaw(serializeColFilters(withColFilter(colFilters, col, v))), [colFilters, setColFiltersRaw])
  const visibleContainers = useMemo(() => applyColFilters(viewContainers, colFilters, today),
    [viewContainers, colFilters, today])
  const counts = useMemo(() => viewCounts(baseContainers, today, prefs.watched, docTiles),
    [baseContainers, today, prefs.watched, docTiles])

  const mv = useQueueMove({
    containers, visible: visibleContainers, canMove: selectable, replaceContainer, load })
  const { selected, setSelected } = mv
  const menus = useTileMenus(replaceContainer)

  // reset TYLKO przy realnej zmianie spółki (nie na mount) — inaczej deep-link z filtrem
  // dostawcy (?dostawca=…) byłby czyszczony przy pierwszym renderze
  const prevModuleRef = useRef(module)
  const { setSupplierId } = f
  useEffect(() => {
    if (prevModuleRef.current === module) return
    prevModuleRef.current = module
    setSelected(new Set())
    mv.setPendingMove(null)
    setSupplierId('')  // filtr dostawcy jest zależny od modułu — czyścimy przy przełączeniu
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [module, setSupplierId])

  // słownik dostawców zawężony do bieżącej zakładki spółki
  useEffect(() => {
    if (module === 'analysis') return
    const params = new URLSearchParams()
    if (moduleCode) params.set('company_code', moduleCode)
    api.get<Supplier[]>(`/api/suppliers?${params}`).then(setSuppliers)
      .catch(err => {   // 403 = rola bez słownika dostawców (agencja celna) — bez czerwonego toastu
        setSuppliers([])
        if ((err as { status?: number })?.status !== 403) showToast(errorMessage(err), 'error')
      })
  }, [module, moduleCode, showToast])

  useEffect(() => {
    const timer = setTimeout(load, 120)
    return () => clearTimeout(timer)
  }, [load])

  useEffect(() => {
    // także logistyka z wglądem we wszystkie spółki — formularz dodania musi wskazać spółkę modułu
    if (seesAll && canEdit) api.get<Company[]>('/api/companies').then(setCompanies).catch(() => {})
  }, [seesAll, canEdit])

  // liczniki kontenerów per spółka na kartach zakładek (odświeżane przy zmianie widoku);
  // licznik Tranzytu — /counts go nie zna, więc lista tranzytów (zwykle krótka) istniejącym API
  const [transitCount, setTransitCount] = useState<number | null>(null)
  useEffect(() => {
    if (!seesAll) return
    // błąd → null: pigułki bez liczby zamiast fałszywych zer (audyt C4)
    api.get<Record<string, number>>('/api/containers/counts').then(setCompanyCounts).catch(() => setCompanyCounts(null))
    api.get<Container[]>(`/api/containers?completed=${archive}&transit=true`)
      .then(list => setTransitCount(list.length)).catch(() => setTransitCount(null))
  }, [seesAll, module, containers, archive])

  const groups = useMemo(() => groupContainers(visibleContainers, groupBy), [visibleContainers, groupBy])
  // każda zakładka to jedna spółka — kolumnę „spółka" pokazujemy tylko we wspólnym fallbacku
  const showCompany = module === 'main'
  // limity dzienne magazynów w nagłówku grupy dnia (ACME n/limit, DLT n/limit)
  const dayRows = useMemo(() => groupBy === 'weekday'
    ? groups.filter(g => g.key).map(g => ({ day: g.key, items: g.items })) : [], [groups, groupBy])
  const warehouseKeys = useMemo(() =>
    summarizeRange([{ day: '', items: visibleContainers }]).warehouses.map(w => w.key), [visibleContainers])
  // sumy narastające tygodnia (Σ od poniedziałku) per dzień — jak dawna szyna tygodnia
  const cumByDay = useMemo(() => new Map(groupByWeek(dayRows)
    .flatMap(w => [...cumulativeByDay(w.days).entries()])), [dayRows])
  const { limitFor } = useUrgency({ rows: dayRows, warehouses: dicts.warehouses, warehouseKeys })
  const conflictIcon = useTransportConflicts({
    enabled: !archive && module !== 'analysis', queryFrom, queryTo, module, containers })

  // zwijanie grup + sekcji planowania (dzień otwarty strzałką mimo globalnie zwiniętej sekcji)
  const { collapsed, setCollapsed, opened, toggleGroup, togglePlanSection } = useGroupCollapse(
    prefs.collapsedPlanning, prefs.togglePlanSection, JSON.stringify([module, queryFrom, queryTo, groupBy]))
  // podpowiedź wyszukiwarki → pokaż rekord w kolejce (rozwiń grupę, przewiń, podświetl)
  const focusSuggestion = useSearchFocus({
    containers, loading, groups, collapsed, setCollapsed,
    collapsedPlanning: prefs.collapsedPlanning, togglePlanSection: prefs.togglePlanSection,
    searchParams, patchParams, setExpandedId, navigate })
  // rozwinięty panel szczegółów zwija się przy zmianie zakresu/modułu/sortu/grupowania
  // (tylko przy realnej zmianie — montaż po F5 nie może zwinąć odtworzonego wiersza)
  const expandScope = useRef<string | null>(null)
  useEffect(() => {
    const scope = JSON.stringify([module, queryFrom, queryTo, sortBy, groupBy])
    if (expandScope.current !== null && expandScope.current !== scope) setExpandedId(null)
    expandScope.current = scope
  }, [module, queryFrom, queryTo, sortBy, groupBy])

  // szuflada kontenera: otwarty kontener w URL (?kontener=<id>), ‹ › po kolejności wierszy
  const drawerId = Number(searchParams.get('kontener')) || null
  const openDrawer = useCallback((id: number) => patchParams({ kontener: String(id) }), [patchParams])
  const closeDrawer = useCallback(() => patchParams({ kontener: '' }), [patchParams])
  const order = useMemo(() => rowOrder(groups, sortItems),
    // sortItems to closure po sortBy
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [groups, sortBy])
  const drawerC = drawerId ? visibleContainers.find(c => c.id === drawerId) ?? null : null
  const drawerIdx = drawerC ? order.indexOf(drawerC.id) : -1
  // „Pełna karta” = osobny ekran; powrót „← Kolejka” przywraca przewinięcie i wiersz
  const openFullCard = useOpenFullCard()
  useReturnScroll(!loading && visibleContainers.length > 0, drawerId)

  // % wypełnienia: liczony TYLKO dla widocznych wierszy (rozwinięte grupy), batchem —
  // patrz queueFill.tsx. Role magazyn/agencja/sprzedaż nie mają dostępu do % wypełnienia.
  const visibleIds = useMemo(() =>
    groups.filter(g => !collapsed.has(g.key)).flatMap(g => g.items.map(c => c.id)), [groups, collapsed])
  const fillEnabled = !archive && module !== 'analysis'
    && user?.role !== 'warehouse' && user?.role !== 'customs' && user?.role !== 'sales'
  const fillMap = useFillSummary(visibleIds, fillEnabled)

  // eksport „cała kolejka" = tylko zakładka/spółka/magazyn/tranzyt, bez filtrów
  const ex = useQueueExport(containerParams, () => {
    const params = new URLSearchParams({ completed: String(archive) })
    if (moduleCode) params.set('company_code', moduleCode)
    if (moduleWarehouse) params.set('warehouse_name', moduleWarehouse)
    params.set('transit', String(moduleTransit))
    return params
  })

  const importCompanyCode = moduleCode ?? (user?.company_code ?? 'BOREALIS')

  // jeden wspólny wiersz nagłówków kolumn dla wszystkich dni (z filtrami w kolumnach)
  const opts = {
    supplierOpts: suppliers.map(s => ({ value: String(s.id), label: s.name })),
    forwarderOpts: dicts.forwarders.map(fw => ({ value: String(fw.id), label: fw.name })),
    warehouseOpts: dicts.warehouses.map(w => ({ value: String(w.id), label: w.name })),
    customsOpts: seesCustoms(user?.role) ? CUSTOMS_STATUSES.map(s => ({ value: s, label: t(`cs_${s}`) })) : [],
    statusOpts: CONTAINER_STATUSES.map(s => ({ value: s, label: t(`st_${s}`) })),
    transportOpts: ['morski', 'lotniczy', 'kolej', 'kola', 'inne'].map(v => ({ value: v, label: t(`transport_${v}`) })),
  }
  const activeFilters = [...activeFilterChips(f, opts, t), ...colFilterChips(colFilters, t, setColFilter)]

  // realna wysokość paska (2 wiersze, może się zawinąć) → --kq-bar-h: tabela przewija się
  // w środku i mieści się pod przyklejonym paskiem (sticky nagłówki kolumn i grup)
  const barRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = barRef.current
    if (!el) return
    const ro = new ResizeObserver(() => el.parentElement?.style.setProperty('--kq-bar-h', `${el.offsetHeight}px`))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  return (
    <main className="page">
      {/* bez widocznego nagłówka (odchudzenie kolejki) — h1 tylko dla czytników */}
      <h1 className="sr-only">{t('queue')}</h1>
      {/* nad tabelą tylko 2 wiersze: (1) firmy + szukaj + akcje, (2) widoki + zakres/filtry/grupuj
          — przy zaznaczeniu wiersz 2 zastępuje pasek akcji masowych */}
      <div className="queue-toolbar kq-toolbar" ref={barRef}>
        <div className="kq-top">
          {seesAll && (
            <CompanyTabs module={module} setModule={setModule} counts={companyCounts} transitCount={transitCount} />
          )}
          <span className="spacer" />
          {module !== 'analysis' && (
            <QueueFilterBar onPickContainer={focusSuggestion}
              f={f} mv={mv} prefs={prefs} ex={ex} module={module} moduleCode={moduleCode}
              archive={archive} canEdit={canEdit} isAdmin={isAdmin}
              loadError={containers.length > 0 ? loadError : '' /* pusta lista → tylko baner niżej */}
              onFound={() => setShowFound(true)} onClearQueue={() => setShowClearQueue(true)}
              onAdd={() => setShowAdd(true)} />
          )}
        </div>
        {module !== 'analysis' && (selectable && selected.size > 0
          ? <BulkActionBar mv={mv} isAdmin={isAdmin} warehouseOptions={warehouseOptions}
                           onAvizo={() => setShowAvizo(true)} onQuote={() => setShowQuote(true)}
                           reload={load} />
          : <EnterpriseFilters f={f} opts={opts} chips={activeFilters} archive={archive}
                               counts={containers.length === 0 && (loading || loadError) ? null : counts} prefs={prefs} />)}
      </div>

      {/* analiza nie jest już pigułką w pasku firm (wejście z menu Analiza) — tytuł widoku tutaj */}
      {module === 'analysis' && (
        <>
          <h2 className="kq-analysis-title"><ChartColumnIcon size="1em" /> {t('moduleAnalysis')} <small>{t('reportsKpi')}</small></h2>
          <AnalysisTab companyCode={ACME} />
        </>
      )}

      {module !== 'analysis' && (
        <>
          {!archive && moduleCode && <PurchaseOrdersPanel companyCode={moduleCode} />}
          {/* W5 #35: ZIP dokumentów miesiąca per spółka (archiwum, admin/logistics) */}
          {archive && canEdit && <MonthlyZipBar companyCode={importCompanyCode} />}
          {loading && containers.length === 0 && <Skeleton rows={6} />}
          {total !== null && total > containers.length && (
            <p className="kq-truncated" role="status">
              {t('kqTruncated').replace('{shown}', String(containers.length)).replace('{total}', String(total))}
            </p>
          )}
          {!loading && loadError && containers.length === 0 && (
            <LoadError message={loadError} onRetry={load} />
          )}
          {!loading && !loadError && containers.length === 0 && (
            <EmptyState icon={Inbox} title={t('empty')} hint={t('queueEmptyHint')}>
              {f.rangeMode !== 'all' && (
                <button className="btn small secondary" onClick={() => f.setRangeMode('all')}>
                  {t('queueEmptyShowAll')}
                </button>
              )}
              {canEdit && !archive && (
                <button className="btn small" onClick={() => setShowAdd(true)}>+ {t('kqAdd')}</button>
              )}
            </EmptyState>
          )}
          {containers.length > 0 && visibleContainers.length === 0 && (
            <EmptyState icon={SearchX} title={t('kqEmptyView')} />
          )}
          {visibleContainers.length > 0 && (
            <div className={loading ? 'reloading' : undefined}>
              <div className={`kq-layout${drawerC ? ' with-drawer' : ''}`}>
              <EnterpriseTable x={{
                groups, groupBy, collapsed, toggleGroup, mv, menus, selectable, canEdit, archive,
                showCompany, compact: !!drawerC, columns: prefs.columns, colOrder: prefs.colOrder, moveCol: prefs.moveCol, dense: prefs.dense, fillMap, docTiles, conflictIcon, expandedId, collapseDetail: () => setExpandedId(null), setStatusFor, cumByDay, drawerId, openDrawer,
                collapsedPlanning: prefs.collapsedPlanning, togglePlanSection, opened,
                watched: prefs.watched, watchReasons: prefs.watchReasons, toggleWatch: prefs.toggleWatch, sortBy, toggleSort: prefs.toggleSort,
                sortItems, openCells: prefs.openCells, toggleCell: prefs.toggleCell,
                openCols: prefs.openCols, toggleColOpen: prefs.toggleColOpen, warehouseKeys, limitFor,
                onHiddenCols: setHiddenCols,
                colFilter: { rows: viewContainers, filters: colFilters, set: setColFilter, today },
              }} />
              {drawerC && (
                <QueueDrawer c={drawerC} fill={fillMap[drawerC.id]} onClose={closeDrawer}
                  watchReason={prefs.watched.has(drawerC.id) ? prefs.watchReasons.get(drawerC.id) ?? '' : undefined}
                  onPrev={drawerIdx > 0 ? () => openDrawer(order[drawerIdx - 1]) : null}
                  onNext={drawerIdx >= 0 && drawerIdx < order.length - 1 ? () => openDrawer(order[drawerIdx + 1]) : null}
                  onStatus={canEdit || isWarehouse ? () => setStatusFor(drawerC) : null}
                  statusLabel={isWarehouse ? t('confirmUnload') : t('changeStatus')}
                  onAvizo={canEdit && !archive ? () => setAvizoOne(drawerC) : null}
                  onFull={() => openFullCard(drawerC.id, order)} />
              )}
              </div>
              <footer className="kq-foot">
                <span>{t('kqFootRecords').replace('{n}', String(visibleContainers.length))
                  .replace('{m}', String(containers.length)).replace('{g}', String(groups.length))}</span>
                <span>{t('kqFootSelected')}: <b>{selected.size}</b></span>
                <HelpTip label={t('kqLegend')} text={t('kqLegendText')} />
                {hiddenCols.length > 0 && <span className="kq-foot-hidden">{t('kqHiddenEmptyCols').replace('{cols}', hiddenCols.join(', '))}</span>}
                <span className="spacer" />
                {refreshedAt && <span>{t('kqFootRefreshed')}: {refreshedAt.toTimeString().slice(0, 5)}</span>}
              </footer>
            </div>
          )}
        </>
      )}

      <MoveConfirmModal mv={mv} containers={containers} />

      {showClearQueue && moduleCode && (
        <ClearQueueModal
          moduleCode={moduleCode}
          onDone={(deleted) => {
            showToast(`${t('clearQueueDone')}: ${deleted}`, 'success')
            setSelected(new Set()); setShowClearQueue(false); load()
          }}
          onClose={() => setShowClearQueue(false)}
        />
      )}
      {(showAvizo || avizoOne) && (
        <AvizoSendModal
          containers={avizoOne ? [avizoOne] : containers.filter(c => selected.has(c.id))}
          onDone={() => { if (!avizoOne) setSelected(new Set()) }}
          onClose={() => { setShowAvizo(false); setAvizoOne(null) }}
        />
      )}
      {showQuote && (
        <QuoteRequestModal
          containers={containers.filter(c => selected.has(c.id))}
          forwarders={dicts.forwarders}
          onDone={() => { setSelected(new Set()); setShowQuote(false) }}
          onClose={() => setShowQuote(false)}
        />
      )}
      {showAdd && (
        <ContainerFormModal
          dicts={dicts}
          // kolejka modułu = spółka modułu (inaczej backend wpisałby spółkę konta albo 422)
          companyOptions={seesAll ? companies.filter(c => !moduleCode || c.code === moduleCode) : undefined}
          onSaved={() => load()}
          onClose={() => setShowAdd(false)}
        />
      )}
      {showFound && (
        <FoundOrderModal
          companyId={seesAll ? (companies.find(c => c.code === moduleCode)?.id ?? null) : null}
          companyCode={moduleCode ?? ''}
          onDone={() => { setShowFound(false); load() }}
          onClose={() => setShowFound(false)}
        />
      )}
      {statusFor && (
        <StatusModal
          container={statusFor}
          warehouseRole={isWarehouse}
          onSaved={replaceContainer}
          onClose={() => setStatusFor(null)}
        />
      )}

      <TileMenus m={menus} warehouseOptions={warehouseOptions} canEdit={canEdit} setPendingMove={mv.setPendingMove}
                 watched={prefs.watched} toggleWatch={prefs.toggleWatch} watchPrompt={prefs.watchPrompt} confirmWatch={prefs.confirmWatch} cancelWatch={prefs.cancelWatch}
                 onDetails={c => setExpandedId(cur => (cur === c.id ? null : c.id))}
                 onStatus={canEdit || isWarehouse ? setStatusFor : null}
                 statusLabel={isWarehouse ? t('confirmUnload') : t('changeStatus')} />

    </main>
  )
}
