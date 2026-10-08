import { createContext, useCallback, useContext } from 'react'
import { plBase } from './i18n/pl.base'
import { plModules } from './i18n/pl.modules'
import { enBase } from './i18n/en.base'
import { enModules } from './i18n/en.modules'
import { ptBase } from './i18n/pt.base'
import { ptModules } from './i18n/pt.modules'

export type Lang = 'pl' | 'en' | 'pt'
export const LANGS: Lang[] = ['pl', 'en', 'pt']

// locale BCP-47 dla Intl (formatowanie dat) — jedno źródło dla wszystkich widoków
const LOCALES: Record<string, string> = { pl: 'pl-PL', en: 'en-GB', pt: 'pt-PT' }
export const localeFor = (lang: string) => LOCALES[lang] ?? 'pl-PL'

type Dict = Record<string, string>

// pl jest źródłem prawdy: TKey = jego klucze; en/pt muszą mieć ten sam kształt
// (części en/pt typowane Partial<Record<TKey>> — literówka w kluczu = błąd tsc)
const pl = { ...plBase, ...plModules }
export type TKey = keyof typeof pl
const en: Record<TKey, string> = { ...pl, ...enBase, ...enModules }
const pt: Record<TKey, string> = { ...en, ...ptBase, ...ptModules }

// teksty funkcji z src/i18n/features/*.ts (jeden plik na funkcję — patrz feature.ts)
const FEATURES = Object.values(import.meta.glob<{ default: { pl: Dict; en?: Dict; pt?: Dict } }>(
  './i18n/features/*.ts', { eager: true })).map(m => m.default)
const featPl: Dict = Object.assign({}, ...FEATURES.map(f => f.pl))
const DICTS: Record<Lang, Dict> = {
  pl: { ...pl, ...featPl },
  en: { ...en, ...featPl, ...Object.assign({}, ...FEATURES.map(f => f.en ?? {})) },
  pt: { ...pt, ...featPl, ...Object.assign({}, ...FEATURES.map(f => f.en ?? {}), ...FEATURES.map(f => f.pt ?? {})) },
}
export { FEATURES }
export { DICTS }

export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({
  lang: 'pl',
  setLang: () => {},
})

// locale bieżącego języka UI (Intl/toLocale*) — zamiast 'pl-PL' na sztywno
export const useLocale = () => localeFor(useContext(LangContext).lang)

// override: język narzucony z zewnątrz (np. formularz awizacji w języku spedytora)
export function useT(override?: string) {
  const { lang: ctx } = useContext(LangContext)
  const lang = override && override in DICTS ? override as Lang : ctx
  // stabilna referencja per język — `t` w zależnościach useCallback/useEffect nie może
  // zmieniać się co render (pętla zapytań → 429 na /dostawcy/:id)
  return useCallback((key: string) => DICTS[lang][key] ?? key, [lang])
}
