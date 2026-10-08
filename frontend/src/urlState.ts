// Wiązanie stanu UI z query string — żeby widok był linkowalny, odświeżalny i „cofalny".
// Zapis przez `replace` (nie push), by drobne zmiany filtrów nie zaśmiecały historii
// przeglądarki; parametr znika, gdy wartość jest pusta/domyślna (czysty URL).
import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

export function useQueryParam(key: string, fallback = ''): [string, (v: string) => void] {
  const [params, setParams] = useSearchParams()
  const value = params.get(key) ?? fallback
  const setValue = useCallback((v: string) => {
    setParams(prev => {
      const next = new URLSearchParams(prev)
      if (v && v !== fallback) next.set(key, v)
      else next.delete(key)
      return next
    }, { replace: true })
  }, [key, fallback, setParams])
  return [value, setValue]
}

// Moduły (zakładki spółek) wybieralne przez URL. „main" to fallback wielospółkowy.
export const SELECTABLE_MODULES = ['acme', 'dlt', 'borealis', 'cobalt', 'pt', 'analysis', 'main']

// Wybór spółki z URL z egzekwowaniem uprawnień: tylko konta widzące wszystkie spółki
// (seesAll) mogą przełączać spółkę adresem; pozostałe są zablokowane na własnej.
export function resolveModule(requested: string, seesAll: boolean, defaultModule: string): string {
  return seesAll && SELECTABLE_MODULES.includes(requested) ? requested : defaultModule
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

// Zwraca wartość tylko gdy to poprawna data ISO (YYYY-MM-DD); inaczej '' (domyślna).
export function isoOrEmpty(v: string | null | undefined): string {
  return v && ISO_DATE.test(v) && !Number.isNaN(Date.parse(v)) ? v : ''
}

// Waliduje zakres dat z URL: obie muszą być ISO, a „od" nie może być po „do".
// Uszkodzona lub odwrócona data → wartość domyślna (['','']), nigdy wyjątek.
export function validDateRange(from: string | null | undefined,
                               to: string | null | undefined): [string, string] {
  const f = isoOrEmpty(from)
  const t = isoOrEmpty(to)
  if (f && t && f > t) return ['', '']
  return [f, t]
}

export function useQueryFlag(key: string): [boolean, (v: boolean) => void] {
  const [raw, setRaw] = useQueryParam(key)
  const setFlag = useCallback((v: boolean) => setRaw(v ? '1' : ''), [setRaw])
  return [raw === '1', setFlag]
}
