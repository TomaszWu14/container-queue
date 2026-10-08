// Strażnik tekstów per funkcja (2026-09-24): klucz nie może się powtarzać między plikami
// funkcji ani nadpisywać kluczy bazowych — cicha kolizja zmieniłaby tekst w innym module.
import { describe, expect, it } from 'vitest'
import { plBase } from './i18n/pl.base'
import { plModules } from './i18n/pl.modules'
import { DICTS, FEATURES } from './i18n'

describe('i18n/features', () => {
  it('klucze funkcji są unikalne i nie kolidują z bazowymi', () => {
    const seen = new Set(Object.keys({ ...plBase, ...plModules }))
    for (const f of FEATURES) for (const k of Object.keys(f.pl)) {
      expect(seen.has(k), `powtórzony klucz: ${k}`).toBe(false)
      seen.add(k)
    }
  })

  it('pliki funkcji są ładowane do słowników (przykład: kopiowanie)', () => {
    expect(FEATURES.length).toBeGreaterThan(0)
    expect([DICTS.pl.copyFailed, DICTS.en.copyFailed, DICTS.pt.copyFailed])
      .toEqual(['Nie udało się skopiować', 'Copy failed', 'Falha ao copiar'])
  })

  it('en/pt mają tylko klucze znane z pl, a brak tłumaczenia = tekst polski', () => {
    for (const f of FEATURES) for (const lang of ['en', 'pt'] as const) {
      for (const k of Object.keys(f[lang] ?? {})) expect(k in f.pl, `${lang}: nieznany klucz ${k}`).toBe(true)
    }
    for (const f of FEATURES) for (const k of Object.keys(f.pl)) {
      expect(DICTS.pt[k]).toBeTruthy()
    }
  })
})
