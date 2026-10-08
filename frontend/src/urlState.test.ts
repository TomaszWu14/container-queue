import { describe, expect, it } from 'vitest'

import { resolveModule, SELECTABLE_MODULES } from './urlState'

describe('resolveModule — wybór spółki z URL z egzekwowaniem uprawnień', () => {
  it('seesAll: przyjmuje poprawny moduł z URL', () => {
    for (const m of SELECTABLE_MODULES) {
      expect(resolveModule(m, true, 'acme')).toBe(m)
    }
  })
  it('seesAll: nieznany moduł → domyślny', () => {
    expect(resolveModule('haker', true, 'acme')).toBe('acme')
    expect(resolveModule('', true, 'acme')).toBe('acme')
  })
  it('konto bez wglądu we wszystkie spółki: URL NIE przełącza spółki (zawsze własna)', () => {
    expect(resolveModule('borealis', false, 'dlt')).toBe('dlt')
    expect(resolveModule('acme', false, 'dlt')).toBe('dlt')
    expect(resolveModule('', false, 'dlt')).toBe('dlt')
  })
})
