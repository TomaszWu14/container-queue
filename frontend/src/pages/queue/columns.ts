// Kolejka Enterprise (plaster 4): wybór kolumn i gęstość — czysta logika + zapis w przeglądarce.
// Domyślnie widać 12 kolumn makiety; pola z dawnej kolejki są dostępne jako opcjonalne.

/** 12 kolumn makiety (kolejność tabeli), „no" = Nr kontenera — zawsze widoczny. */
export const BASE_COLUMNS = ['no', 'supplier', 'vessel', 'eta', 'notify', 'status', 'customs', 'wh',
  'fwd', 'order', 'dem', 'fill', 'docs'] as const
/** Pola z dawnej kolejki (wideColumns sprzed plastra 1), domyślnie ukryte. */
export const EXTRA_COLUMNS = ['etd', 'transport', 'deliveryNote', 'incomingNo', 'purchaseNote',
  'docFlow', 'sentReq', 'sentNo', 'sentStatus'] as const
export const LOCKED_COLUMN = 'no'
/** Klucz tłumaczenia etykiety kolumny (popover „Kolumny"; tabela używa tych samych). */
export const COLUMN_LABEL: Record<string, string> = {
  no: 'containerNo', supplier: 'supplier', vessel: 'vessel', eta: 'eta', notify: 'kqColDelivery',
  status: 'status', customs: 'customs', wh: 'warehouse', fwd: 'forwarder', order: 'kqColOrder',
  dem: 'kqColDemurrage', fill: 'kqColFill', docs: 'kqColDocs', etd: 'etdCol', transport: 'transport',
  deliveryNote: 'kqColDeliveryNote', incomingNo: 'incomingDeliveryNo', purchaseNote: 'purchaseNote',
  docFlow: 'documentFlow', sentReq: 'kqColSentReq', sentNo: 'sentNoCol', sentStatus: 'kqColSentStatus',
}
/** Kolumny niewidoczne dla roli — spedytor nie widzi odprawy (seesCustoms, 2026-09-28). */
export const ROLE_HIDDEN_COLUMNS: Readonly<Record<string, ReadonlySet<string>>> = {
  forwarder: new Set(['customs']),
}
/** Szuflada otwarta → chowamy kolumny niskiego priorytetu (reguła z plastra 3). */
export const COMPACT_HIDDEN = new Set(['fwd', 'fill'])

const COLS_KEY = 'kqColumns'
const DENSE_KEY = 'kqDense'
const KNOWN = new Set<string>([...BASE_COLUMNS, ...EXTRA_COLUMNS])

/** Widoczne klucze: zapis użytkownika (filtrowany do znanych) albo domyślne; Nr zawsze. */
export function visibleColumns(saved: string[] | null): Set<string> {
  const keys = saved ? saved.filter(k => KNOWN.has(k)) : [...BASE_COLUMNS]
  return new Set([LOCKED_COLUMN, ...keys])
}

export function toggleColumn(current: Set<string>, key: string): string[] {
  if (key === LOCKED_COLUMN) return [...current]
  const next = new Set(current)
  if (next.has(key)) next.delete(key); else next.add(key)
  return [...next]
}

// localStorage bywa niedostępny (tryb prywatny / zablokowany) — wtedy domyślne
export function readColumns(): string[] | null {
  try {
    const raw = JSON.parse(localStorage.getItem(COLS_KEY) ?? 'null')
    return Array.isArray(raw) ? raw.filter((v): v is string => typeof v === 'string') : null
  } catch { return null }
}
export function writeColumns(keys: string[] | null) {
  try {
    if (keys) localStorage.setItem(COLS_KEY, JSON.stringify(keys)); else localStorage.removeItem(COLS_KEY)
  } catch { /* brak storage — ustawienie tylko na tę sesję */ }
}
// Kompaktowy (28px) domyślny dla osób bez zapisanego wyboru; zapisane '0' (Komfortowy) szanujemy
export function readDense(): boolean {
  try { return localStorage.getItem(DENSE_KEY) !== '0' } catch { return true }
}
export function writeDense(dense: boolean) {
  try { localStorage.setItem(DENSE_KEY, dense ? '1' : '0') } catch { /* j.w. */ }
}

/** Kolumny puste w całej widocznej tabeli (każdy wiersz bez wartości) → nie są renderowane. */
export function emptyColumns<T>(cols: { key: string; empty?: (c: T) => boolean }[], items: T[]): Set<string> {
  if (items.length === 0) return new Set()
  return new Set(cols.filter(col => col.empty && items.every(col.empty)).map(col => col.key))
}

// ---- kolejność kolumn (przeciąganie nagłówków / ↑↓ w menu „Widok") — profil konta przez setPref ----
export const ORDER_KEY = 'kqColOrder'
/** Kolejność domyślna = kolejność w kodzie (makieta, potem pola dodatkowe). */
export const DEFAULT_ORDER: readonly string[] = [...BASE_COLUMNS, ...EXTRA_COLUMNS]

/** Klucze `keys` (kolejność z kodu) ułożone wg zapisu: Nr zawsze pierwszy, klucze zapisu, których
 *  już nie ma, pomijane; kolumna spoza zapisu (nowa w kodzie) staje za swoim domyślnym poprzednikiem. */
export function applyOrder(keys: readonly string[], saved: readonly string[] | null): string[] {
  if (!saved) return [...keys]
  const known = new Set(keys)
  const out = [...new Set(saved)].filter(k => known.has(k) && k !== LOCKED_COLUMN)
  keys.forEach((k, i) => {
    if (k === LOCKED_COLUMN || out.includes(k)) return
    const prev = keys.slice(0, i).reverse().find(p => out.includes(p))
    out.splice(prev ? out.indexOf(prev) + 1 : 0, 0, k)
  })
  return known.has(LOCKED_COLUMN) ? [LOCKED_COLUMN, ...out] : out
}

/** Przeniesienie `key` przed/za `target` (upuszczenie nagłówka). Nr nieruchomy i zawsze pierwszy. */
export function moveBeside(order: readonly string[], key: string, target: string, after: boolean): string[] {
  if (key === target || key === LOCKED_COLUMN || !order.includes(key) || !order.includes(target)) return [...order]
  const out = order.filter(k => k !== key)
  out.splice(out.indexOf(target) + (after ? 1 : 0), 0, key)
  return applyOrder(order, out)
}

/** Zamiana miejscami z sąsiadem z listy `among` (przyciski ↑/↓ w sekcji menu „Widok"). */
export function moveStep(order: readonly string[], key: string, dir: -1 | 1, among: readonly string[]): string[] {
  const list = order.filter(k => among.includes(k) && k !== LOCKED_COLUMN)
  const i = list.indexOf(key)
  const other = i < 0 ? undefined : list[i + dir]
  if (!other) return [...order]
  return order.map(k => (k === key ? other : k === other ? key : k))
}

// uszkodzony / obcy kształt w prefs (np. obiekt, liczby) → kolejność domyślna
export function readOrder(): string[] | null {
  try {
    const raw = JSON.parse(localStorage.getItem(ORDER_KEY) ?? 'null')
    return Array.isArray(raw) ? raw.filter((v): v is string => typeof v === 'string') : null
  } catch { return null }
}
