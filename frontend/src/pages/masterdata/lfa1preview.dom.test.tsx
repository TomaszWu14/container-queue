// @vitest-environment jsdom
// Podgląd importu LFA1: zakładki z licznikami, zmiany pole po polu, pełny eksport, „+N więcej”.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import Lfa1Preview, { isLfa1Result, type Lfa1Result } from './Lfa1Preview'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
afterEach(cleanup)

const data: Lfa1Result = {
  counts: { total: 5, new: 0, changed: 1, disappeared: 3, errors: 1 },
  new: [],
  changed: [{ id: 1, sap_code: '100', name: 'TRANSLOG', changes: [{ field: 'name', old: 'OLD', new: 'TRANSLOG' }] }],
  disappeared: [{ id: 2, sap_code: '200', name: 'STARY' }],
  errors: [{ row: 4, sap_code: '', name: 'BEZ KODU', reason: 'brak kodu SAP' }],
}

describe('Lfa1Preview', () => {
  it('startuje na pierwszej niepustej zakładce, pokazuje zmianę stara → nowa', () => {
    render(<Lfa1Preview data={data} fullExport={false} onFullExport={() => {}} />)
    expect(screen.getByText('lfa1Tab_changed (1)').className).toBe('active')
    expect(screen.getByText('OLD').tagName).toBe('S')
    expect(screen.getByText('name:')).toBeTruthy()   // atrapa t() → brak tłumaczenia → surowe pole
  })

  it('zniknięci: ucięta lista (+N), opis zależny od „pełny eksport”, checkbox zgłasza zmianę', () => {
    const onFull = vi.fn()
    const { rerender } = render(<Lfa1Preview data={data} fullExport={false} onFullExport={onFull} />)
    fireEvent.click(screen.getByText('lfa1Tab_disappeared (3)'))
    expect(screen.getByText('STARY')).toBeTruthy()
    expect(screen.getByText('lfa1More')).toBeTruthy()
    expect(screen.getByText('lfa1DisappearedPartial')).toBeTruthy()
    fireEvent.click(screen.getByRole('checkbox'))
    expect(onFull).toHaveBeenCalledWith(true)
    rerender(<Lfa1Preview data={data} fullExport onFullExport={onFull} />)
    expect(screen.getByText('lfa1DisappearedFull')).toBeTruthy()
  })

  it('isLfa1Result odróżnia wynik LFA1 od innych importów', () => {
    expect(isLfa1Result(data)).toBe(true)
    expect(isLfa1Result({ counts: { new: 1 } })).toBe(false)
  })
})
