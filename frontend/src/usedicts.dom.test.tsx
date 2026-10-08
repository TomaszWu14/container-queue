// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { ToastProvider } from './feedback'
import { useDicts } from './components'

vi.mock('./i18n', () => ({ useT: () => (key: string) => key }))

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('./api', () => ({
  api: { get: apiGet },
  errorMessage: (e: unknown) => String(e),
}))

afterEach(() => { cleanup(); apiGet.mockReset() })

function Probe() {
  const { suppliers } = useDicts()
  return <span>ok:{suppliers.length}</span>
}

function Probe2() {
  const { suppliers, warehouses, forwarders } = useDicts()
  return <span>s:{suppliers.length} w:{warehouses.length} f:{forwarders.length}</span>
}

describe('useDicts — błąd ładowania słowników', () => {
  it('pusta lista + toast błędu (nie połyka po cichu)', async () => {
    apiGet.mockRejectedValue(new Error('boom'))
    render(<ToastProvider><Probe /></ToastProvider>)
    // błąd inny niż 403 → toast z komunikatem, selecty zostają puste
    await waitFor(() => expect(screen.getAllByText('Error: boom').length).toBeGreaterThan(0))
    expect(screen.getByText('ok:0')).toBeTruthy()
  })

  it('403 jednego słownika (agencja: dostawcy) nie zeruje pozostałych i nie daje toastu', async () => {
    apiGet.mockImplementation((path: string) => path === '/api/suppliers'
      ? Promise.reject(Object.assign(new Error('forbidden'), { status: 403 }))
      : Promise.resolve([{ id: 1, name: 'X' }]))
    render(<ToastProvider><Probe2 /></ToastProvider>)
    await waitFor(() => expect(screen.getByText('s:0 w:1 f:1')).toBeTruthy())
    expect(screen.queryByText(/forbidden/)).toBeNull()
  })

  it('sukces: brak toastu błędu', async () => {
    apiGet.mockResolvedValue([])
    render(<ToastProvider><Probe /></ToastProvider>)
    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    expect(screen.queryByText(/Error/)).toBeNull()
  })
})
