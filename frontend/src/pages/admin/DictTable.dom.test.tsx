// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import { DictTable, dash, dupKey } from './shared'

// Regresja: nagłówek rozjeżdżał się z danymi, bo table-layout:auto mierzył thead i tbody
// niezależnie. Siatkę trzyma <colgroup> — musi mieć tyle <col> co kolumn i tyle co komórek.
afterEach(cleanup)

describe('DictTable', () => {
  it('colgroup ma po jednej kolumnie na nagłówek i na komórkę wiersza', () => {
    const { container } = render(
      <DictTable cols={['Nazwa', { label: 'Aktywny', width: '90px' }, { width: '80px' }]}>
        <tr><td>Port Gdańsk</td><td>tak</td><td /></tr>
      </DictTable>,
    )
    const cols = container.querySelectorAll('colgroup col')
    expect(cols).toHaveLength(3)
    expect((cols[1] as HTMLElement).style.width).toBe('90px')
    expect(container.querySelectorAll('thead th')).toHaveLength(3)
    expect(container.querySelectorAll('tbody td')).toHaveLength(3)
    expect(container.querySelector('table')!.className).toContain('dict-table')
  })

  it('dash zwraca myślnik tylko dla pustej wartości', () => {
    const { container } = render(<p>{dash('')}{dash(null)}{dash('x')}</p>)
    expect(container.querySelectorAll('.dict-empty')).toHaveLength(2)
    expect(container.textContent).toBe('——x')
  })
})

describe('dupKey', () => {
  it('skleja warianty tej samej nazwy, rozróżnia różne', () => {
    const k = (n: string) => dupKey(n)
    expect(k('SHANGHAI')).toBe(k('Shanghai'))
    expect(k('Xiamen Port')).toBe(k('xiamen-port'))
    expect(k('Gdansk')).toBe(k('Gdańsk'))
    expect(k('Ningbo')).not.toBe(k('Ningbo Zhoushan'))
  })

  it('ta sama nazwa w innej spolce to nie duplikat — scalac wolno tylko w obrebie spolki', () => {
    expect(dupKey('Magazyn A', 1)).not.toBe(dupKey('Magazyn A', 2))
  })
})
