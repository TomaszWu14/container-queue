// audyt UI C14/A17: licznik „Kolejka” nie dolicza magazynu DLT (podzbiór Acme) drugi raz
import { describe, expect, it } from 'vitest'
import { activeTotal } from './Sidebar'

describe('activeTotal', () => {
  it('sumuje spółki, pomija klucz DLT', () => {
    expect(activeTotal({ ACME: 288, DLT: 96, BOREALIS: 1, PT: 1 })).toBe(290)
  })
  it('pusta odpowiedź → 0', () => {
    expect(activeTotal({})).toBe(0)
  })
})
