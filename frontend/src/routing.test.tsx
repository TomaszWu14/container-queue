import { describe, expect, it } from 'vitest'

import type { Role } from './types'
import { canAccess, fillTarget, homeFor, LEGACY_REDIRECTS, type ViewKey } from './routing'

// Nowe ścieżki, na które wolno wskazywać redirectom (spójność mapy).
const NEW_PATHS = new Set([
  '/', '/kalendarz', '/zamowienia', '/zamowienia/:id', '/spedycja', '/odprawa',
  '/wyceny', '/sledzenie', '/reklamacje', '/reklamacje/archiwum', '/reklamacje/:id',
  '/kolejka/archiwum', '/kontenery/:id', '/administracja', '/kolejka',
])

describe('fillTarget — podstawianie parametrów w redirectach', () => {
  it('podstawia :id', () => {
    expect(fillTarget('/kontenery/:id', { id: '123' })).toBe('/kontenery/123')
    expect(fillTarget('/zamowienia/:id', { id: '7' })).toBe('/zamowienia/7')
  })
  it('ścieżki bez parametrów zostają bez zmian', () => {
    expect(fillTarget('/kalendarz', {})).toBe('/kalendarz')
  })
  it('brakujący parametr zostawia placeholder (nie wysypuje się)', () => {
    expect(fillTarget('/kontenery/:id', {})).toBe('/kontenery/:id')
  })
})

describe('LEGACY_REDIRECTS — mapa starych→nowych ścieżek', () => {
  it('każdy cel jest znaną nową ścieżką', () => {
    for (const target of Object.values(LEGACY_REDIRECTS)) {
      expect(NEW_PATHS.has(target), `nieznany cel redirectu: ${target}`).toBe(true)
    }
  })
  it('zgodność parametrów: stara i nowa ścieżka mają te same :param', () => {
    const paramsOf = (p: string) => (p.match(/:[A-Za-z0-9_]+/g) ?? []).sort()
    for (const [oldP, newP] of Object.entries(LEGACY_REDIRECTS)) {
      expect(paramsOf(oldP), `rozjazd parametrów: ${oldP} → ${newP}`).toEqual(paramsOf(newP))
    }
  })
  it('pokrywa wszystkie zmienione stare adresy', () => {
    for (const old of ['/dashboard', '/calendar', '/orders', '/orders/:id', '/forwarding',
      '/customs', '/quotes', '/tracking', '/complaints', '/complaints/archive',
      '/complaints/:id', '/archive', '/container/:id', '/admin', '/dzis']) {
      expect(LEGACY_REDIRECTS[old], `brak redirectu dla ${old}`).toBeTruthy()
    }
  })
})

describe('canAccess — dostęp per widok wg roli (bez zmiany semantyki)', () => {
  const roles: Role[] = ['admin', 'logistics', 'forwarder', 'warehouse', 'customs']
  // oczekiwana macierz = dotychczasowa logika tras
  const expected: Record<ViewKey, Role[]> = {
    kolejka: roles, kontener: roles, awizo: roles,
    dashboard: ['admin', 'logistics', 'forwarder'],
    'kolejka-arch': ['admin', 'logistics', 'forwarder'],
    zamowienia: ['admin', 'logistics'],   // = backend PurchasingReaders (+ zakupy)
    spedycja: ['admin', 'logistics', 'forwarder'],
    wyceny: ['admin', 'logistics', 'forwarder'],
    kalendarz: ['admin', 'logistics', 'forwarder', 'warehouse'],
    sledzenie: ['admin', 'logistics', 'forwarder', 'warehouse'],
    reklamacje: ['admin', 'logistics', 'forwarder', 'warehouse'],
    odprawa: ['admin', 'logistics'],
    administracja: ['admin'],
  }
  for (const key of Object.keys(expected) as ViewKey[]) {
    for (const role of roles) {
      const allowed = expected[key].includes(role)
      it(`${role} ${allowed ? 'MA' : 'NIE ma'} dostępu do ${key}`, () => {
        expect(canAccess(role, key)).toBe(allowed)
      })
    }
  }

  it('admin ma dostęp do administracji, pozostali nie', () => {
    expect(canAccess('admin', 'administracja')).toBe(true)
    expect(canAccess('logistics', 'administracja')).toBe(false)
  })
  it('customs widzi tylko kolejkę/kontener/awizo', () => {
    expect(canAccess('customs', 'kolejka')).toBe(true)
    expect(canAccess('customs', 'kalendarz')).toBe(false)
    expect(canAccess('customs', 'reklamacje')).toBe(false)
  })

  describe('purchasing — jawna biała lista (bez dziedziczenia z negatywnych bramek)', () => {
    for (const key of ['kolejka', 'kontener', 'zamowienia', 'spedycja'] as ViewKey[]) {
      it(`MA dostęp do ${key}`, () => expect(canAccess('purchasing', key)).toBe(true))
    }
    // krytyczne: Odprawa/Wyceny nie mogą wpaść po cichu do nowej roli
    for (const key of ['odprawa', 'wyceny', 'dashboard', 'kalendarz', 'sledzenie',
      'reklamacje', 'kolejka-arch', 'administracja', 'awizo'] as ViewKey[]) {
      it(`NIE ma dostępu do ${key}`, () => expect(canAccess('purchasing', key)).toBe(false))
    }
  })
})

describe('homeFor — strona startowa wg roli', () => {
  it('transport (logistics) startuje w kolejce', () => {
    expect(homeFor('logistics')).toBe('/kolejka')
  })
  it('admin i spedytor startują na pulpicie', () => {
    expect(homeFor('admin')).toBe('/')
    expect(homeFor('forwarder')).toBe('/')
  })
  it('role bez pulpitu (w tym magazyn — dawniej /dzis) startują w kolejce', () => {
    for (const r of ['warehouse', 'customs', 'purchasing'] as Role[]) {
      expect(homeFor(r)).toBe('/kolejka')
    }
  })
})
