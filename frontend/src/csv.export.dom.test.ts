// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { csvCell, downloadCsv, toCsv } from './api'
import { statsToCsv } from './pages/complaintUtils'
import { huInventoryCsv } from './pages/palletcalls/HuInventorySection'

describe('csvCell / toCsv (wspólny eksport CSV)', () => {
  it('neutralizuje formuły = + - @ apostrofem', () => {
    expect(csvCell('=HYPERLINK("http://x","klik")')).toBe(`"'=HYPERLINK(""http://x"",""klik"")"`)
    expect(csvCell('+48 123')).toBe("'+48 123")
    expect(csvCell('-1+1')).toBe("'-1+1")
    expect(csvCell('@SUM(A1)')).toBe("'@SUM(A1)")
  })
  it('liczby (także ujemne) zostają liczbami, null → pusto', () => {
    expect(csvCell(-5)).toBe('-5')
    expect(csvCell(null)).toBe('')
    expect(csvCell(undefined)).toBe('')
  })
  it('escapuje średnik, cudzysłów i nową linię', () => {
    expect(toCsv([['a;b', 'x"y', 'l1\nl2'], [1, 2, 3]])).toBe('"a;b";"x""y";"l1\nl2"\n1;2;3')
  })
  it('eksporty stron idą przez ochronę przed formułami', () => {
    const hu = huInventoryCsv([{ produkt: '=cmd', hu: 'H1', ilosc: 1, in_dlt: true, called: false,
      call_number: '', call_status: '', mismatch: false }])
    expect(hu.split('\n')[1]).toBe("'=cmd;H1;1;tak;nie;;;nie")
    const st = statsToCsv({ months: 12, suppliers: [{ name: '@evil', containers: 1, with_complaint: 0, pct: 0 }],
      carriers: [], costs: [] }, { supplier: 'S', carrier: 'C', containers: 'K', withComplaint: 'W',
      pct: '%', currency: 'Cur', claim: 'Cl', recovered: 'R', recoveryPct: 'RP' })
    expect(st).toContain("'@evil;1;0;0")
  })
})

describe('downloadCsv', () => {
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })
  it('BOM + zwolnienie URL dopiero po pętli zdarzeń', async () => {
    vi.useFakeTimers()
    let blob: Blob | undefined
    const create = vi.fn((b: Blob) => { blob = b; return 'blob:x' })
    const revoke = vi.fn()
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    downloadCsv('a.csv', 'x;y')
    expect(click).toHaveBeenCalled()
    expect(revoke).not.toHaveBeenCalled()
    vi.runAllTimers()
    expect(revoke).toHaveBeenCalledWith('blob:x')
    expect([...new Uint8Array(await blob!.arrayBuffer())]).toEqual([0xef, 0xbb, 0xbf, 0x78, 0x3b, 0x79])
  })
})
