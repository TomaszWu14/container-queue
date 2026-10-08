import { describe, expect, it } from 'vitest'
import { applyOrder, BASE_COLUMNS, emptyColumns, moveBeside, moveStep, toggleColumn, visibleColumns } from './columns'

describe('zwężanie pustych kolumn', () => {
  const cols = [
    { key: 'a', empty: (v: number) => v === 0 },
    { key: 'b', empty: (v: number) => v < 5 },
    { key: 'c' },   // bez predykatu — nigdy nie zwężana
  ]
  it('pusta = pusta w każdym widocznym wierszu', () => {
    expect([...emptyColumns(cols, [1, 2])]).toEqual(['b'])
    expect([...emptyColumns(cols, [0, 0])].sort()).toEqual(['a', 'b'])
  })
  it('brak wierszy = nic nie zwężamy', () => {
    expect(emptyColumns(cols, []).size).toBe(0)
  })
})

describe('wybór kolumn', () => {
  it('domyślnie 12 kolumn makiety', () => {
    expect([...visibleColumns(null)].sort()).toEqual([...BASE_COLUMNS].sort())
  })
  it('zapis filtrowany do znanych kluczy, Nr kontenera zawsze widoczny', () => {
    expect([...visibleColumns(['vessel', 'bogus', 'etd'])].sort()).toEqual(['etd', 'no', 'vessel'])
  })
  it('przełączanie: dodaje/usuwa, Nr kontenera nie do odznaczenia', () => {
    const cur = visibleColumns(['vessel'])
    expect(toggleColumn(cur, 'vessel').sort()).toEqual(['no'])
    expect(toggleColumn(cur, 'transport').sort()).toEqual(['no', 'transport', 'vessel'])
    expect(toggleColumn(cur, 'no').sort()).toEqual(['no', 'vessel'])
  })
})

describe('kolejność kolumn', () => {
  const keys = ['no', 'a', 'b', 'c', 'd']
  it('brak zapisu = kolejność z kodu', () => {
    expect(applyOrder(keys, null)).toEqual(keys)
  })
  it('zapis: Nr zawsze pierwszy, zniknięte/duplikaty pomijane, nowa kolumna za domyślnym poprzednikiem', () => {
    expect(applyOrder(keys, ['c', 'no', 'a', 'gone', 'c'])).toEqual(['no', 'c', 'd', 'a', 'b'])
    expect(applyOrder(keys, [])).toEqual(keys)
    expect(applyOrder(['a', 'b'], ['b', 'no', 'a'])).toEqual(['b', 'a'])   // bez Nr (np. inne grupowanie)
  })
  it('przeniesienie przed/za cel; Nr nieruchomy, upuszczenie przed Nr = tuż za nim', () => {
    expect(moveBeside(keys, 'd', 'a', false)).toEqual(['no', 'd', 'a', 'b', 'c'])
    expect(moveBeside(keys, 'a', 'c', true)).toEqual(['no', 'b', 'c', 'a', 'd'])
    expect(moveBeside(keys, 'no', 'c', true)).toEqual(keys)
    expect(moveBeside(keys, 'c', 'no', false)).toEqual(['no', 'c', 'a', 'b', 'd'])
    expect(moveBeside(keys, 'x', 'a', false)).toEqual(keys)
  })
  it('↑/↓ zamienia z sąsiadem w obrębie sekcji; skraj i Nr bez zmian', () => {
    expect(moveStep(keys, 'c', -1, ['a', 'c'])).toEqual(['no', 'c', 'b', 'a', 'd'])
    expect(moveStep(keys, 'a', -1, keys)).toEqual(keys)
    expect(moveStep(keys, 'd', 1, keys)).toEqual(keys)
    expect(moveStep(keys, 'no', 1, keys)).toEqual(keys)
  })
})
