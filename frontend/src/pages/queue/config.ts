// Stałe i typy kolejki wyniesione z QueuePage.tsx (moduły/spółki, tryby zakresu, sort).
import type { Container } from '../../types'
import type { Country } from '../../holidays'

export const ACME = 'ACME'

// osobne kolejki per spółka + DLT (magazyn) + wspólny fallback „main" i analiza
export type Module = 'acme' | 'dlt' | 'borealis' | 'cobalt' | 'pt' | 'tranzyt' | 'main' | 'analysis'

// klucz modułu → kod spółki (filtr backendu). DLT to spółka Acme + filtr magazynu.
export const MODULE_CODE: Partial<Record<Module, string>> = {
  acme: 'ACME', dlt: 'ACME', borealis: 'BOREALIS', cobalt: 'COBALT', pt: 'PT',
}

// moduł DLT = kontenery spółki Acme kierowane do magazynu DLT (Acme agreguje ACME + DLT)
// kraj kalendarza świąt w kolejce (backend: warehouse.country, domyślnie PL)
export const moduleCountry = (m: Module): Country => m === 'pt' ? 'PT' : 'PL'

export const MODULE_WAREHOUSE: Partial<Record<Module, string>> = { dlt: 'DLT' }

// tranzyt nie jest spółką ani magazynem — to flaga na kontenerze. Pozostałe zakładki
// wysyłają jawne transit=false, żeby tranzyty nie wpadały do zwykłych kolejek.
export const MODULE_TRANSIT: Partial<Record<Module, boolean>> = { tranzyt: true }

// magazyny rozładunku dostępne z menu kontekstowego per zakładka (Iberia — nie zmieniamy)
export const WAREHOUSE_OPTIONS: Partial<Record<Module, string[]>> = {
  acme: ['DLT', 'ACME'],
  dlt: ['DLT', 'ACME'],
  borealis: ['ACME', 'BOREALIS'],
  cobalt: ['ACME', 'COBALTSPORT'],
}

export type RangeMode = 'all' | 'fromToday' | 'month' | 'week' | 'custom'

// stała mapa trybu zakresu → klucz tłumaczenia (wyczerpująca po RangeMode)
export const RANGE_LABEL: Record<RangeMode, string> = {
  all: 'rangeAll', fromToday: 'rangeFromToday',
  month: 'rangeMonth', week: 'rangeWeek', custom: 'rangeCustom',
}

// multi-sort w dniu — akcesory kolumn sortowalnych
export const SORT_ACCESSOR: Record<string, (c: Container) => string | number> = {
  supplier: c => c.supplier_name ?? '',
  vessel: c => c.vessel ?? '',
  eta: c => c.eta ?? '9999',
  containerNo: c => c.container_no,
  forwarder: c => c.forwarder_name ?? '',
  status: c => c.status,
  orderNumbers: c => c.order_numbers || c.order_number || '',
  warehouse: c => c.warehouse_name ?? '',
  notifyDate: c => c.notify_date ?? '9999',
  customs: c => c.customs_status,
  demurrage: c => c.demurrage_deadline ?? '9999',
}

export type SortKey = { key: string; dir: 1 | -1 }

export type GroupBy = 'weekday' | 'warehouse' | 'status'

// menu kontekstowe kafelka (magazyn / data / kebab) — kontener + pozycja kursora
export type TileMenuPos = { c: Container; x: number; y: number }

// note = wpis do historii; fromDate = zmiana z kalendarza (nie kasuj zaznaczenia)
export type PendingMove = { ids: number[]; day: string; note?: string; fromDate?: boolean }
