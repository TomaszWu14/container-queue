// Teksty jednej funkcji w jednym pliku (2026-09-24): src/i18n/features/<funkcja>.ts.
// Każda funkcja dopisywała klucze na końcu wspólnych *.modules.ts — dwa równoległe PR-y
// prawie zawsze się zderzały. Własny plik na funkcję = brak konfliktów.
// en/pt mogą być częściowe (brak = tekst polski); literówka w kluczu en/pt = błąd tsc.
export type FeatureTexts<K extends string> = {
  pl: Record<K, string>
  en?: Partial<Record<K, string>>
  pt?: Partial<Record<K, string>>
}

export function defineFeature<K extends string>(texts: FeatureTexts<K>): FeatureTexts<K> {
  return texts
}
