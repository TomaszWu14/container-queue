// @vitest-environment jsdom
// Strażnik (2026-09-24, zmiany 2026-10-01): numer od lewej (równo z wierszami jednego numeru),
// licznik „› N” na końcu komórki, liczy unikalne numery; rozwinięta — ⧉ przy każdym numerze
// i „Kopiuj wszystkie” pod listą; zwinięta pokazuje numer zaznaczony w filtrze kolumny.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

import { MultiCell } from './cells'

afterEach(cleanup)

const RAW = '4500624089\n4500624788, 4500625542-2, 4500624788'   // duplikat z importu

describe('MultiCell — licznik i kopiuj wszystkie', () => {
  it('numer pierwszy, licznik unikalnych na końcu; kopiuj wszystkie i ⧉ każdego po rozwinięciu', () => {
    const { container } = render(<MultiCell raw={RAW} open={false} onToggle={() => {}} copyable />)
    expect(container.querySelector('.multi-cell')?.firstElementChild?.className).toContain('multi-values')
    expect(container.querySelector('.multi-cell')?.lastElementChild?.textContent).toBe('3')
    expect(screen.queryByTitle('copyAll')).toBeNull()
    cleanup()
    const { container: open } = render(<MultiCell raw={RAW} open onToggle={() => {}} copyable />)
    expect([...open.querySelectorAll('.multi-values > span:not(.multi-all) .copy-btn')]
      .map(b => b.getAttribute('data-copy'))).toEqual(['4500624089', '4500624788', '4500625542-2'])
    expect(screen.getByTitle('copyAll').getAttribute('data-copy'))
      .toBe('4500624089\n4500624788\n4500625542-2')
    expect(screen.getByRole('button', { expanded: true }).textContent).toBe('3')
  })

  it('jeden numer — bez licznika i bez kopiuj wszystkie', () => {
    const { container } = render(<MultiCell raw="4500624089" open={false} onToggle={() => {}} copyable />)
    expect(container.querySelector('.multi-more')).toBeNull()
    expect(screen.queryByTitle('copyAll')).toBeNull()
  })

  it('zwinięta pokazuje numer z filtra kolumny, podświetlony', () => {
    const { container } = render(<MultiCell raw={RAW} open={false} onToggle={() => {}}
                                            hits={['4500625542-2']} />)
    expect(container.querySelector('.multi-values')?.textContent).toBe('4500625542-2')
    expect(container.querySelector('.multi-hit')?.textContent).toBe('4500625542-2')
  })
})
