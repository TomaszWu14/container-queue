// Pomocnicze operacje na datach w UTC (bez wpływu strefy czasowej) oraz
// numeracja tygodni ISO 8601. Współdzielone przez widoki kolejki/kalendarza.

import { DICTS, type Lang } from './i18n'

export const toISO = (d: Date) => d.toISOString().slice(0, 10)
export const parseISO = (s: string) => new Date(`${s}T00:00:00Z`)
// „dziś" wg zegara ściennego usera, nie UTC — toISOString() między północą
// a ~2:00 w PL zwracało wczorajszą datę (tryb „od dziś", domyślny dzień kolejki)
export const todayISO = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// „2026-07-08" | „2026-07-08T12:34:56" → „08.07.2026"; puste/null → „—"
// konwencja suity: w UI daty ZAWSZE dd.mm.rrrr (ISO tylko w API i <input type="date">).
// `approx` = data szacowana → „~08.07.2026".
export const formatDate = (v: string | null | undefined, approx = false): string => {
  if (!v) return '—'
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v)
  return m ? `${approx ? '~' : ''}${m[3]}.${m[2]}.${m[1]}` : v
}

// zakres dat: „21.09.2026–27.09.2026"; `short` → „21.09–27.09.2026", ale tylko gdy
// oba końce w tym samym roku (przełom roku zawsze pełny). Ten sam dzień → jedna data.
export const formatDateRange = (from: string | null | undefined, to: string | null | undefined,
                                short = false): string => {
  if (!from && !to) return '—'
  if (!from || !to || from.slice(0, 10) === to.slice(0, 10)) return formatDate(from || to)
  const a = formatDate(from)
  return `${short && from.slice(0, 4) === to.slice(0, 4) ? a.slice(0, 5) : a}–${formatDate(to)}`
}

// nagłówek dnia: „25 września 2026 – piątek" (data-only, bez przesunięcia strefy)
export const formatDayLong = (iso: string, locale: string): string => {
  const d = parseISO(iso.slice(0, 10))
  if (Number.isNaN(d.getTime())) return iso
  const f = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(locale, { ...o, timeZone: 'UTC' }).format(d)
  return `${f({ day: 'numeric', month: 'long', year: 'numeric' })}, ${f({ weekday: 'long' })}`
}

// „2026-07-08T12:34:56" (naiwny UTC z backendu) → „08.07.2026 14:34" CZASU LOKALNEGO;
// sama data → „08.07.2026"; puste → „—". Poprzednio wycinaliśmy surowy podłańcuch,
// więc każdy znacznik czasu był o offset strefy za wcześnie (relTime obok liczyło dobrze).
export const formatDateTime = (v: string | null | undefined): string => {
  if (!v) return '—'
  const iso = v.replace(' ', 'T')
  if (!iso.includes('T')) return formatDate(v)
  const d = parseServerTs(iso)
  if (Number.isNaN(d.getTime())) return v
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// liczba z polskim formatem: przecinek dziesiętny + spacja grupująca (konwencja suity).
// `d` = stała liczba miejsc po przecinku (jak toFixed); pominięte → naturalna precyzja.
export const formatNum = (n: number | string | null | undefined, d?: number): string => {
  if (n == null || Number.isNaN(Number(n))) return '—'
  return new Intl.NumberFormat('pl-PL',
    d != null ? { minimumFractionDigits: d, maximumFractionDigits: d } : {}).format(Number(n))
}

// Znaczniki czasu z backendu to NAIWNY UTC (bez „Z"/offsetu, np. „2026-09-06T12:34:56").
// Bez tej normalizacji `new Date(iso)` traktuje je jako czas LOKALNY → arytmetyka „X temu"
// i próg „stale" są przesunięte o offset strefy (latem +2h w PL). Doklej „Z" tam, gdzie
// backend nie podał strefy; wartości z „Z"/offsetem oraz daty-only zostaw bez zmian.
export const parseServerTs = (iso: string): Date => {
  const hasZone = /[Zz]$|[+-]\d\d:?\d\d$/.test(iso)
  return new Date(hasZone || !iso.includes('T') ? iso : `${iso}Z`)
}

// świeżość trackingu w formie względnej: „przed chwilą / 5 min temu / 2 godz. temu /
// 3 dni temu / nigdy". `now` jako argument (nie Date.now() wewnątrz) — deterministyczne w testach.
export function relTime(iso: string | null | undefined, lang: string, now: number = Date.now()): string {
  const dict = DICTS[(lang as Lang) in DICTS ? (lang as Lang) : 'pl']
  const at = (key: string, n: number) => dict[key].replace('{n}', String(n))
  if (!iso) return dict.relNever
  const diffMs = now - parseServerTs(iso).getTime()
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return dict.relJustNow
  if (min < 60) return at('relMinAgo', min)
  const hrs = Math.floor(min / 60)
  if (hrs < 24) return at('relHoursAgo', hrs)
  const days = Math.floor(hrs / 24)
  return at('relDaysAgo', days)
}

// zakres miesiąca z (rok, miesiąc) — wariant liczbowy monthRange dla kalendarza
export function monthRangeYM(year: number, month: number): [string, string] {
  return [toISO(new Date(Date.UTC(year, month, 1))),
          toISO(new Date(Date.UTC(year, month + 1, 0)))]
}

export function isoWeek(s: string): number {
  const d = parseISO(s)
  const day = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - day)          // czwartek bieżącego tygodnia
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  return Math.ceil((((d.getTime() - yearStart.getTime()) / 864e5) + 1) / 7)
}

// rok tygodnia ISO (rok, do którego należy czwartek danego tygodnia) — różni się
// od roku kalendarzowego na przełomie roku (np. 2027-01-01 to tydzień 53/2026)
export function isoWeekYear(s: string): number {
  const d = parseISO(s)
  const day = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - day)
  return d.getUTCFullYear()
}

export function weekRange(s: string): [string, string] {
  const d = parseISO(s)
  const day = d.getUTCDay() || 7
  const monday = new Date(d); monday.setUTCDate(d.getUTCDate() - (day - 1))
  const sunday = new Date(monday); sunday.setUTCDate(monday.getUTCDate() + 6)
  return [toISO(monday), toISO(sunday)]
}

export function monthRange(s: string): [string, string] {
  const d = parseISO(s)
  const first = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1))
  const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0))
  return [toISO(first), toISO(last)]
}

export function shiftMonth(s: string, by: number): string {
  const d = parseISO(s)
  return toISO(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + by, 1)))
}

export function shiftDays(s: string, by: number): string {
  const d = parseISO(s)
  d.setUTCDate(d.getUTCDate() + by)
  return toISO(d)
}

// poniedziałek tygodnia ISO o podanym numerze w danym roku
export function isoWeekMonday(year: number, week: number): string {
  const jan4 = new Date(Date.UTC(year, 0, 4))
  const day = jan4.getUTCDay() || 7
  const week1Monday = new Date(jan4); week1Monday.setUTCDate(jan4.getUTCDate() - (day - 1))
  week1Monday.setUTCDate(week1Monday.getUTCDate() + (week - 1) * 7)
  return toISO(week1Monday)
}

// liczba tygodni ISO w roku (52 lub 53)
export function isoWeeksInYear(year: number): number {
  return isoWeek(`${year}-12-28`)
}

// --- <input type="date"> a niedopisany rok ---
// Chrome/Edge emitują zmianę po KAŻDEJ cyfrze roku: „2” → 0002-11-09, „20” → 0020-11-09.
// Pola, których onChange od razu coś robi (przeniesienie awizacji, filtr, zapytanie), reagowały
// na bzdurną datę. Globalny strażnik (main.tsx) zatrzymuje takie zdarzenia, zanim dotrą do Reacta,
// a przy opuszczeniu pola / Enter uzupełnia rok 1–2-cyfrowy do 20xx („26” → 2026).
// Zakres = backend (schemas/base.py OP_YEAR_MIN/MAX).
export const DATE_YEAR_MIN = 2000
export const DATE_YEAR_MAX = 2099

/** Data z rokiem spoza zakresu operacyjnego (np. niedopisany „0002”); pusta = czyszczenie pola, OK. */
export const isOutOfRangeDate = (v: string): boolean => {
  const m = /^(\d{4,})-\d{2}-\d{2}$/.exec(v)
  return !!m && (Number(m[1]) < DATE_YEAR_MIN || Number(m[1]) > DATE_YEAR_MAX)
}

/** „0026-11-09” → „2026-11-09”; rok ≥ 100 i inne wartości bez zmian. */
export const expandShortYear = (v: string): string => {
  const m = /^(\d{4})-(\d{2}-\d{2})$/.exec(v)
  return m && Number(m[1]) < 100 ? `${2000 + Number(m[1])}-${m[2]}` : v
}

const isDateInput = (t: EventTarget | null): t is HTMLInputElement =>
  t instanceof HTMLInputElement && t.type === 'date'

/** Strażnik na window w fazie capture (przed Reactem); zwraca funkcję odinstalowania. */
export function installDateInputGuard(): () => void {
  const block = (e: Event) => {
    if (isDateInput(e.target) && isOutOfRangeDate(e.target.value)) e.stopImmediatePropagation()
  }
  const complete = (e: Event) => {
    const el = e.target
    if (!isDateInput(el) || (e instanceof KeyboardEvent && e.key !== 'Enter')) return
    const full = expandShortYear(el.value)
    if (full === el.value) return
    // setter z prototypu: React śledzi wartość własnym setterem i inaczej nie zauważyłby zmiany
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(el, full)
    el.dispatchEvent(new Event('input', { bubbles: true }))
    el.dispatchEvent(new Event('change', { bubbles: true }))
  }
  const pairs: [string, (e: Event) => void][] =
    [['input', block], ['change', block], ['focusout', complete], ['keydown', complete]]
  pairs.forEach(([type, fn]) => window.addEventListener(type, fn, true))
  return () => pairs.forEach(([type, fn]) => window.removeEventListener(type, fn, true))
}
