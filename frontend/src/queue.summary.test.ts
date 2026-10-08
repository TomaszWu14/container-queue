// Helpery widoku tygodniowego (4a): rozbicie per magazyn, podsumowanie zakresu
// i rozbijanie wielowartościowych numerów PO/SENT.
import { describe, expect, it } from 'vitest'
import {
  bandWarehouses, cleanMultiline, NO_WAREHOUSE, splitMulti, summarizeRange, warehouseClass, warehouseKey,
} from './pages/queueSummary'
import type { Container } from './types'

const make = (id: number, warehouse_name: string | null, is_delayed = false) =>
  ({ id, container_no: `C${id}`, warehouse_name, is_delayed } as unknown as Container)

describe('warehouseKey', () => {
  it('dopasowuje po słowie, nie po całej nazwie', () => {
    expect(warehouseKey('DLT Radom')).toBe('DLT')
    expect(warehouseKey('Magazyn BOREALIS')).toBe('BOREALIS')
  })

  it('„ACME DLT" to DLT — DLT sprawdzamy pierwszy (jak whRowClass)', () => {
    expect(warehouseKey('ACME DLT')).toBe('DLT')
  })

  it('nieznany magazyn zostaje pod własną nazwą, pusty dostaje klucz zastępczy', () => {
    expect(warehouseKey('Nowy Skład')).toBe('NOWY SKŁAD')
    expect(warehouseKey(null)).toBe(NO_WAREHOUSE)
    expect(warehouseKey('   ')).toBe(NO_WAREHOUSE)
  })

  it('kolor dostają tylko znane magazyny', () => {
    expect(warehouseClass('DLT')).toBe('wh-dlt')
    expect(warehouseClass('NOWY SKŁAD')).toBe('wh-other')
    expect(warehouseClass(NO_WAREHOUSE)).toBe('wh-other')
  })
})

describe('summarizeRange', () => {
  const rows = [
    { day: '2025-12-15', items: [make(1, 'ACME'), make(2, 'DLT', true)] },
    { day: '2025-12-16', items: [] },
    { day: '2025-12-17', items: [make(3, 'ACME'), make(4, null)] },
  ]

  it('liczy sumę, dni z dostawami i opóźnienia', () => {
    const s = summarizeRange(rows)
    expect(s.total).toBe(4)
    expect(s.activeDays).toBe(2)
    expect(s.totalDays).toBe(3)
    expect(s.late).toBe(1)
  })

  it('magazyny malejąco po liczbie, z udziałem procentowym', () => {
    const s = summarizeRange(rows)
    expect(s.warehouses.map(w => [w.key, w.n, w.pct]))
      .toEqual([['ACME', 2, 50], [NO_WAREHOUSE, 1, 25], ['DLT', 1, 25]])
  })

  it('kontener bez magazynu wchodzi do sumy — kafle zgadzają się z licznikiem dnia', () => {
    const s = summarizeRange(rows)
    expect(s.warehouses.reduce((a, w) => a + w.n, 0)).toBe(s.total)
  })

  it('pusty zakres nie dzieli przez zero', () => {
    const s = summarizeRange([{ day: '2025-12-20', items: [] }])
    expect(s).toMatchObject({ total: 0, activeDays: 0, late: 0, warehouses: [] })
  })
})

describe('bandWarehouses', () => {
  it('zwraca zestaw z całego zakresu, magazyn bez dostaw z zerem', () => {
    const chips = bandWarehouses([make(1, 'ACME')], ['ACME', 'DLT'])
    expect(chips.map(w => [w.key, w.n])).toEqual([['ACME', 1], ['DLT', 0]])
  })
})

describe('splitMulti', () => {
  it('rozbija po nowej linii, przecinku i średniku', () => {
    expect(splitMulti('4500617421\n4500617412, 4500617989; 4500617862'))
      .toEqual(['4500617421', '4500617412', '4500617989', '4500617862'])
  })

  it('puste pole i puste fragmenty nie tworzą wartości', () => {
    expect(splitMulti('')).toEqual([])
    expect(splitMulti(null)).toEqual([])
    expect(splitMulti('4500617421,,\n')).toEqual(['4500617421'])
  })

  it('Excelowy _x000D_ (CR z importu xlsx) też jest separatorem', () => {
    expect(splitMulti('180030275_x000D_180030276_x000D_180030280'))
      .toEqual(['180030275', '180030276', '180030280'])
    expect(splitMulti('180030275_x000D_\r180030276')).toEqual(['180030275', '180030276'])
  })
})

describe('cleanMultiline', () => {
  it('_x000D_ → realny \\n, bez CR', () => {
    expect(cleanMultiline('odprawa RSL_x000D_tłum ok')).toBe('odprawa RSL\ntłum ok')
    expect(cleanMultiline('a\r\nb')).toBe('a\nb')
    expect(cleanMultiline(null)).toBe('')
  })
})
