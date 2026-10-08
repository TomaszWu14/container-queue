// Święta państwowe PL i PT (stałe + ruchome od Wielkanocy) — lustro backend/app/holidays.py.
// Zgodność pilnuje wspólny snapshot holidays.snapshot.json (test vitest + pytest).

function easter(year: number): Date {
  // Niedziela wielkanocna (algorytm Meeusa/Jonesa/Butchera)
  const a = year % 19
  const b = Math.floor(year / 100)
  const c = year % 100
  const d = Math.floor(b / 4)
  const e = b % 4
  const f = Math.floor((b + 8) / 25)
  const g = Math.floor((b - f + 1) / 3)
  const h = (19 * a + b - d - g + 15) % 30
  const i = Math.floor(c / 4)
  const k = c % 4
  const l = (32 + 2 * e + 2 * i - h - k) % 7
  const m = Math.floor((a + 11 * h + 22 * l) / 451)
  const month = Math.floor((h + l - 7 * m + 114) / 31)
  const day = ((h + l - 7 * m + 114) % 31) + 1
  return new Date(Date.UTC(year, month - 1, day))
}

export type Country = 'PL' | 'PT'

// jedno źródło: data → nazwa; zbiór świąt = klucze tej mapy
const FIXED: Record<Country, Record<string, string>> = {
  PL: {
    '01-01': 'Nowy Rok', '01-06': 'Trzech Króli', '05-01': 'Święto Pracy',
    '05-03': 'Święto Konstytucji 3 Maja', '08-15': 'Wniebowzięcie NMP',
    '11-01': 'Wszystkich Świętych', '11-11': 'Święto Niepodległości',
    '12-24': 'Wigilia', '12-25': 'Boże Narodzenie', '12-26': 'Drugi dzień Bożego Narodzenia',
  },
  PT: {
    '01-01': 'Ano Novo', '04-25': 'Dia da Liberdade', '05-01': 'Dia do Trabalhador',
    '06-10': 'Dia de Portugal', '08-15': 'Assunção de Nossa Senhora',
    '10-05': 'Implantação da República', '11-01': 'Todos os Santos',
    '12-01': 'Restauração da Independência', '12-08': 'Imaculada Conceição', '12-25': 'Natal',
  },
}
// święta ruchome: przesunięcie w dniach od Niedzieli Wielkanocnej
const FROM_EASTER: Record<Country, [number, string][]> = {
  PL: [[0, 'Wielkanoc'], [1, 'Poniedziałek Wielkanocny'], [49, 'Zielone Świątki'], [60, 'Boże Ciało']],
  PT: [[-2, 'Sexta-feira Santa'], [0, 'Páscoa'], [60, 'Corpo de Deus']],
}
const nameCache = new Map<string, Map<string, string>>()

export function holidayNames(year: number, country: Country = 'PL'): Map<string, string> {
  const key = `${country}${year}`
  const cached = nameCache.get(key)
  if (cached) return cached
  const map = new Map<string, string>()
  for (const [md, name] of Object.entries(FIXED[country])) map.set(`${year}-${md}`, name)
  const es = easter(year)
  for (const [days, name] of FROM_EASTER[country]) {
    const d = new Date(es)
    d.setUTCDate(d.getUTCDate() + days)
    map.set(d.toISOString().slice(0, 10), name)
  }
  nameCache.set(key, map)
  return map
}

// nazwa święta dla daty ISO lub null (weekendy nie mają nazwy)
export function holidayName(isoDay: string, country: Country = 'PL'): string | null {
  return holidayNames(Number(isoDay.slice(0, 4)), country).get(isoDay) ?? null
}

export function isWeekend(isoDay: string): boolean {
  const weekday = new Date(`${isoDay}T00:00:00Z`).getUTCDay()
  return weekday === 0 || weekday === 6
}

export function isHoliday(isoDay: string, country: Country = 'PL'): boolean {
  return holidayNames(Number(isoDay.slice(0, 4)), country).has(isoDay)
}

// Licznik dni roboczych w roku: dni które NIE są weekendem ani świętem.
const workdayCache = new Map<string, number>()
export function workingDaysInYear(year: number, country: Country = 'PL'): number {
  const key = `${country}${year}`
  const cached = workdayCache.get(key)
  if (cached != null) return cached
  const holidays = holidayNames(year, country)
  const iso = (d: Date) => d.toISOString().slice(0, 10)
  let count = 0
  for (const d = new Date(Date.UTC(year, 0, 1)); d.getUTCFullYear() === year; d.setUTCDate(d.getUTCDate() + 1)) {
    const wd = d.getUTCDay()
    if (wd !== 0 && wd !== 6 && !holidays.has(iso(d))) count++
  }
  workdayCache.set(key, count)
  return count
}

// Godziny robocze = dni robocze × długość dnia pracy (domyślnie 8h wg Kodeksu pracy).
export function workingHoursInYear(year: number, hoursPerDay = 8): number {
  return workingDaysInYear(year) * hoursPerDay
}
