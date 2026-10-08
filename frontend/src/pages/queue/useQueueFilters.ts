// Filtry i zakres dat kolejki — całość w query string (linkowalne, odświeżalne, „wstecz").
// Wyniesione z QueuePage.tsx; hook nie zna modułu ani uprawnień, tylko parametry URL.
import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQueryFlag, useQueryParam } from '../../urlState'
import { monthRange, todayISO, weekRange } from '../../dates'
import type { RangeMode } from './config'
import { QUEUE_VIEWS, type QueueView } from './enterprise'

// komplet filtrów wyzerowany — „Wyczyść wszystkie" i wybór podpowiedzi wyszukiwarki
export const NO_FILTERS: Record<string, string> = {
  szukaj: '', status: '', odprawa: '', dostawca: '', spedytor: '', magazyn: '',
  statek: '', transport: '', zamowienia: '', dostawa_uwagi: '', nr_dostawy: '',
  zakupy: '', przeplyw: '', nr_sent: '', eta_od: '', eta_do: '', opoznione: '', kolumny: '',
}

// defaultRange: tryb zakresu, gdy URL go nie podaje (kolejka = tydzień, archiwum = wszystko)
export function useQueueFilters(defaultRange: RangeMode = 'all') {
  const [searchParams, setSearchParams] = useSearchParams()
  // jedna złożona zmiana query — kilka parametrów naraz. Bez tego kolejne setSearchParams
  // w jednym handlerze nadpisują się (każde czyta ten sam „prev", ostatnie wygrywa).
  const patchParams = useCallback((patch: Record<string, string>) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      for (const [k, v] of Object.entries(patch)) { if (v) next.set(k, v); else next.delete(k) }
      return next
    }, { replace: true })
  }, [setSearchParams])

  const [q, setQ] = useQueryParam('szukaj')
  const [status, setStatus] = useQueryParam('status')
  const [customs, setCustoms] = useQueryParam('odprawa')
  const [supplierId, setSupplierId] = useQueryParam('dostawca')
  const [forwarderId, setForwarderId] = useQueryParam('spedytor')
  const [warehouseId, setWarehouseId] = useQueryParam('magazyn')
  // #5 — filtry per kolumna (tekst/enum/zakres), wszystkie w URL
  const [vessel, setVessel] = useQueryParam('statek')
  const [transport, setTransport] = useQueryParam('transport')
  const [orderNo, setOrderNo] = useQueryParam('zamowienia')
  const [deliveryNote, setDeliveryNote] = useQueryParam('dostawa_uwagi')
  const [incomingNo, setIncomingNo] = useQueryParam('nr_dostawy')
  const [purchaseNote, setPurchaseNote] = useQueryParam('zakupy')
  const [docFlow, setDocFlow] = useQueryParam('przeplyw')
  const [sentNo, setSentNo] = useQueryParam('nr_sent')
  const [etaFrom, setEtaFrom] = useQueryParam('eta_od')
  const [etaTo, setEtaTo] = useQueryParam('eta_do')
  const [delayedOnly, setDelayedOnly] = useQueryFlag('opoznione')
  // filtry w nagłówkach kolumn „jak w Excelu" (JSON, po stronie klienta) — columnFilter/values.ts
  const [colFiltersRaw, setColFiltersRaw] = useQueryParam('kolumny')
  // zakładka widoku (Kolejka Enterprise); legacy ?moje=1 = zakładka „★ Moje"
  const viewParam = searchParams.get('widok') ?? 'all'
  const legacyMine = searchParams.get('moje') === '1'
  const setView = useCallback((v: QueueView) =>
    patchParams({ widok: v === 'all' ? '' : v, moje: '' }), [patchParams])
  const view: QueueView = (QUEUE_VIEWS as string[]).includes(viewParam) && viewParam !== 'all'
    ? viewParam as QueueView : (legacyMine ? 'mine' : 'all')
  const [hideFree, setHideFree] = useQueryFlag('bez_wolnych')
  // filtr „specjalne" — tylko kontenery z flagą 🚩
  const [specialOnly, setSpecialOnly] = useQueryFlag('pod-klienta')

  // legacy ?date=… (stare zakładki / link z kalendarza) → zakres „custom" z jednym dniem
  const legacyDate = searchParams.get('date') ?? ''
  // fallback = tryb domyślny, NIE trafia do URL (setRangeMode(domyślny) usuwa parametr)
  const [okresParam, setRangeMode] = useQueryParam('okres', defaultRange)
  const [dataParam, setAnchor] = useQueryParam('data')
  const [odParam, setDateFrom] = useQueryParam('od')
  const [doParam, setDateTo] = useQueryParam('do')
  const rangeMode = (okresParam !== defaultRange || !legacyDate
    ? okresParam : 'custom') as RangeMode
  const anchor = dataParam || legacyDate || todayISO()
  const dateFrom = odParam || legacyDate
  const dateTo = doParam || legacyDate

  // efektywny zakres dat zapytania wynika z trybu; „zakres" korzysta z pól ręcznych
  const [queryFrom, queryTo] =
    rangeMode === 'month' ? monthRange(anchor)
      : rangeMode === 'week' ? weekRange(anchor)
        : rangeMode === 'custom' ? [dateFrom, dateTo]
          : rangeMode === 'fromToday' ? [todayISO(), '']
            : ['', '']

  const clearAllFilters = () => patchParams(NO_FILTERS)

  return {
    searchParams, patchParams, clearAllFilters,
    q, setQ, status, setStatus, customs, setCustoms, supplierId, setSupplierId,
    forwarderId, setForwarderId, warehouseId, setWarehouseId, vessel, setVessel,
    transport, setTransport, orderNo, setOrderNo, deliveryNote, setDeliveryNote,
    incomingNo, setIncomingNo, purchaseNote, setPurchaseNote, docFlow, setDocFlow,
    sentNo, setSentNo, etaFrom, setEtaFrom, etaTo, setEtaTo, delayedOnly, setDelayedOnly,
    colFiltersRaw, setColFiltersRaw, view, setView, hideFree, setHideFree, specialOnly, setSpecialOnly,
    rangeMode, setRangeMode, anchor, setAnchor, dateFrom, setDateFrom, dateTo, setDateTo,
    queryFrom, queryTo,
  }
}

export type QueueFilters = ReturnType<typeof useQueueFilters>

// wspólne parametry zapytania o kontenery — jedno źródło dla listy i eksportu
export function containerQuery(f: QueueFilters, archive: boolean, moduleCode?: string,
                               moduleWarehouse?: string, moduleTransit = false) {
  const params = new URLSearchParams({ completed: String(archive) })
  if (moduleCode) params.set('company_code', moduleCode)
  if (moduleWarehouse) params.set('warehouse_name', moduleWarehouse)
  params.set('transit', String(moduleTransit))
  if (f.q) params.set('q', f.q)
  if (f.status) params.set('status', f.status)
  if (f.customs) params.set('customs_status', f.customs)
  if (f.supplierId) params.set('supplier_id', f.supplierId)
  if (f.forwarderId) params.set('forwarder_id', f.forwarderId)
  if (f.warehouseId) params.set('warehouse_id', f.warehouseId)
  if (f.delayedOnly) params.set('delayed', 'true')
  if (f.queryFrom) params.set('date_from', f.queryFrom)
  if (f.queryTo) params.set('date_to', f.queryTo)
  if (f.vessel) params.set('vessel', f.vessel)
  if (f.transport) params.set('transport', f.transport)
  if (f.orderNo) params.set('order_numbers', f.orderNo)
  if (f.deliveryNote) params.set('delivery_note', f.deliveryNote)
  if (f.incomingNo) params.set('incoming_delivery_no', f.incomingNo)
  if (f.purchaseNote) params.set('purchase_note', f.purchaseNote)
  if (f.docFlow) params.set('document_flow', f.docFlow)
  if (f.sentNo) params.set('sent_number', f.sentNo)
  if (f.etaFrom) params.set('eta_from', f.etaFrom)
  if (f.etaTo) params.set('eta_to', f.etaTo)
  return params
}

type Opt = { value: string; label: string }
export type FilterOpts = {
  statusOpts: Opt[]; customsOpts: Opt[]; supplierOpts: Opt[]; forwarderOpts: Opt[]
  warehouseOpts: Opt[]; transportOpts: Opt[]
}

// decyzja 15 — pasek aktywnych filtrów (chipy), źródło prawdy = query string; ×
// usuwa pojedynczy filtr, „Wyczyść wszystkie" zeruje komplet (ten sam zestaw co
// istniejący „Wyczyść filtry" + wyszukiwarka + „Tylko opóźnione").
export function activeFilterChips(f: QueueFilters, o: FilterOpts, t: (k: string) => string) {
  const opt = (opts: Opt[], v: string) => opts.find(x => x.value === v)?.label ?? v
  const items: { key: string; label: string; onClear: () => void }[] = []
  if (f.q) items.push({ key: 'szukaj', label: `${t('search')}: ${f.q}`, onClear: () => f.setQ('') })
  if (f.status) items.push({ key: 'status', label: `${t('status')}: ${opt(o.statusOpts, f.status)}`, onClear: () => f.setStatus('') })
  if (f.customs) items.push({ key: 'odprawa', label: `${t('customs')}: ${opt(o.customsOpts, f.customs)}`, onClear: () => f.setCustoms('') })
  if (f.supplierId) items.push({ key: 'dostawca', label: `${t('supplier')}: ${opt(o.supplierOpts, f.supplierId)}`, onClear: () => f.setSupplierId('') })
  if (f.forwarderId) items.push({ key: 'spedytor', label: `${t('forwarder')}: ${opt(o.forwarderOpts, f.forwarderId)}`, onClear: () => f.setForwarderId('') })
  if (f.warehouseId) items.push({ key: 'magazyn', label: `${t('warehouse')}: ${opt(o.warehouseOpts, f.warehouseId)}`, onClear: () => f.setWarehouseId('') })
  if (f.vessel) items.push({ key: 'statek', label: `${t('vessel')}: ${f.vessel}`, onClear: () => f.setVessel('') })
  if (f.transport) items.push({ key: 'transportf', label: `${t('transport')}: ${opt(o.transportOpts, f.transport)}`, onClear: () => f.setTransport('') })
  if (f.orderNo) items.push({ key: 'zamowienia', label: `${t('orderNumbers')}: ${f.orderNo}`, onClear: () => f.setOrderNo('') })
  if (f.deliveryNote) items.push({ key: 'dostawa_uwagi', label: `${t('deliveryNote')}: ${f.deliveryNote}`, onClear: () => f.setDeliveryNote('') })
  if (f.incomingNo) items.push({ key: 'nr_dostawy', label: `${t('incomingDeliveryNo')}: ${f.incomingNo}`, onClear: () => f.setIncomingNo('') })
  if (f.purchaseNote) items.push({ key: 'zakupy', label: `${t('purchaseNote')}: ${f.purchaseNote}`, onClear: () => f.setPurchaseNote('') })
  if (f.docFlow) items.push({ key: 'przeplyw', label: `${t('documentFlow')}: ${f.docFlow}`, onClear: () => f.setDocFlow('') })
  if (f.sentNo) items.push({ key: 'nr_sent', label: `${t('sentNoCol')}: ${f.sentNo}`, onClear: () => f.setSentNo('') })
  if (f.etaFrom || f.etaTo) items.push({
    key: 'eta', label: `${t('eta')}: ${f.etaFrom || '…'}–${f.etaTo || '…'}`,
    onClear: () => { f.setEtaFrom(''); f.setEtaTo('') },
  })
  if (f.delayedOnly) items.push({ key: 'opoznione', label: t('onlyDelayed'), onClear: () => f.setDelayedOnly(false) })
  return items
}
