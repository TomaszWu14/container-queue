// @vitest-environment jsdom
// Decyzja 2026-09-30: ilości przyjętej ani zafakturowanej nie wpisuje się ręcznie —
// panel jest tylko do odczytu, a pusta we wszystkich wierszach kolumna „Przyjęto” znika.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

vi.mock('../i18n', () => ({ useT: () => (key: string) => key }))

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({
  api: { get: apiGet },
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

import OrderLinesPanel from './OrderLinesPanel'
import type { Container } from '../types'

afterEach(() => { cleanup(); apiGet.mockReset() })

const LINE = { order_number: 'PO1', position: '10', material: 'M1', description: '',
  ordered_qty: '5', received_qty: '', invoiced_qty: '3', receipt_id: null,
  status: 'none', status_invoice: 'partial' }

describe('OrderLinesPanel — tylko do odczytu', () => {
  it('bez pól edycji; pusta kolumna „Przyjęto” jest ukryta, zafakturowano widoczne', async () => {
    apiGet.mockResolvedValue([LINE])
    const { container } = render(<OrderLinesPanel container={{ id: 1 } as Container} />)
    expect(await screen.findByText('3')).toBeTruthy()
    expect(container.querySelector('input, button, textarea')).toBeNull()
    expect(screen.queryByText('olReceived')).toBeNull()
    expect(screen.getByText('olInvoiced')).toBeTruthy()
  })

  it('przyjęto z istniejących danych: kolumna widoczna, pusta komórka jako „—”', async () => {
    apiGet.mockResolvedValue([{ ...LINE, received_qty: '4', status: 'partial' },
      { ...LINE, position: '20', invoiced_qty: '' }])
    const { container } = render(<OrderLinesPanel container={{ id: 1 } as Container} />)
    expect(await screen.findByText('4')).toBeTruthy()
    expect(screen.getByText('olReceived')).toBeTruthy()
    expect(container.querySelector('input, button, textarea')).toBeNull()
    expect(screen.getAllByText('—')).toHaveLength(2)   // przyjęto + zafakturowano w wierszu 20
  })
})
