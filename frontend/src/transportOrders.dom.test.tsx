// @vitest-environment jsdom
// CODE-008: logika akcji zleceń transportowych w jednym miejscu (useTransportOrderActions) —
// karta kontenera i strona Spedycji nie mają własnych kopii przejść statusów.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { TransportOrder } from './types'

const { apiPost } = vi.hoisted(() => ({ apiPost: vi.fn(() => Promise.resolve({})) }))
vi.mock('./api', () => ({ api: { post: apiPost }, errorMessage: (e: unknown) => String(e) }))
vi.mock('./ConfirmDialog', () => ({ useConfirm: () => ({ prompt: () => Promise.resolve('po telefonie') }) }))

import { useTransportOrderActions } from './transportOrders'

const sources = import.meta.glob(['./collaboration.tsx', './pages/ForwardingPage.tsx'],
  { query: '?raw', import: 'default', eager: true }) as Record<string, string>

afterEach(() => { cleanup(); apiPost.mockClear() })

const order = (status: TransportOrder['status']) => ({ id: 5, status }) as TransportOrder

function Harness({ role, status, onBehalf, onDone = () => {} }: {
  role: string; status: TransportOrder['status']; onBehalf?: boolean; onDone?: () => void
}) {
  const a = useTransportOrderActions({ role, onDone, onBehalf })
  return <div>{a.actions(order(status))}{a.rejectRow}{a.error && <p>{a.error}</p>}</div>
}

describe('akcje zleceń transportowych', () => {
  it('jedna implementacja: endpoint zmiany statusu tylko w transportOrders.tsx', () => {
    for (const [path, src] of Object.entries(sources)) {
      expect(src, path).not.toContain('/api/transport-orders/${orderId}/status')
      expect(src, path).toContain('useTransportOrderActions')
    }
  })

  it('spedytor: przyjmij → ZAAKCEPTOWANE, odrzuć wymaga powodu', async () => {
    const onDone = vi.fn()
    render(<Harness role="forwarder" status="WYSTAWIONE" onDone={onDone} />)
    fireEvent.click(screen.getByRole('button', { name: 'Odrzuć' }))
    const rejects = screen.getAllByRole('button', { name: 'Odrzuć' })
    const confirm = rejects[rejects.length - 1] as HTMLButtonElement
    expect(confirm.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Powód odrzucenia'), { target: { value: 'brak auta' } })
    fireEvent.click(confirm)
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/transport-orders/5/status',
      { status: 'ODRZUCONE', reason: 'brak auta' }))
    expect(onDone).toHaveBeenCalled()
  })

  it('logistyka: akceptacja w imieniu tylko z onBehalf, WYKONANE → potwierdź', async () => {
    const { rerender } = render(<Harness role="logistics" status="WYSTAWIONE" />)
    expect(screen.queryByRole('button')).toBeNull()
    rerender(<Harness role="logistics" status="WYSTAWIONE" onBehalf />)
    fireEvent.click(screen.getByRole('button', { name: 'Zaakceptuj za spedytora' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/transport-orders/5/status',
      { status: 'ZAAKCEPTOWANE', reason: 'po telefonie' }))
    rerender(<Harness role="logistics" status="WYKONANE" />)
    expect(screen.getByRole('button', { name: 'Potwierdź' })).toBeTruthy()
  })

  it('BIZ-008: logistyka cofa „wykonane” i wystawia ponownie odrzucone — z powodem', async () => {
    const { rerender } = render(<Harness role="logistics" status="WYKONANE" />)
    fireEvent.click(screen.getByRole('button', { name: 'Cofnij do realizacji' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/transport-orders/5/status',
      { status: 'W_REALIZACJI', reason: 'po telefonie' }))
    rerender(<Harness role="logistics" status="ODRZUCONE" />)
    fireEvent.click(screen.getByRole('button', { name: 'Wystaw ponownie' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/transport-orders/5/status',
      { status: 'WYSTAWIONE', reason: 'po telefonie' }))
    // spedytor nie ma korekt
    rerender(<Harness role="forwarder" status="ODRZUCONE" />)
    expect(screen.queryByRole('button')).toBeNull()
  })
})
