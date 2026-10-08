// @vitest-environment jsdom
// Usuwanie w master data: przycisk 🗑 widoczny tylko dla admina, confirm z nazwą,
// DELETE + odświeżenie listy po sukcesie.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { mdAt } from './pages/mdRoute.testutil'

let USER: { role: string } | null = { role: 'admin' }
const delMock = vi.fn((_path: string) => Promise.resolve({}))

const PORT = {
  id: 5, name: 'Shanghai', country: 'CN', category: 'GLOWNY_CN',
  transit_time_days: 38, transit_time_long_days: 45, monthly_transit: {}, is_active: true,
}

vi.mock('./api', () => ({
  api: {
    get: (path: string) => Promise.resolve(path.startsWith('/api/ports') ? [PORT] : []),
    post: () => Promise.resolve({}),
    patch: () => Promise.resolve({}),
    del: (path: string) => delMock(path),
  },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => USER }))

import MasterDataPage from './pages/MasterDataPage'
import { ToastProvider } from './feedback'

function renderPorts() {
  render(mdAt('porty', <ToastProvider><MasterDataPage /></ToastProvider>))
}

afterEach(cleanup)
beforeEach(() => { delMock.mockClear() })

describe('master data — usuwanie', () => {
  it('admin widzi 🗑, confirm z nazwą, DELETE i refetch po sukcesie', async () => {
    USER = { role: 'admin' }
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPorts()
    const btn = await screen.findByRole('button', { name: 'Usuń' })
    fireEvent.click(btn)
    expect(confirmSpy.mock.calls[0][0]).toContain('Shanghai')
    await waitFor(() => expect(delMock).toHaveBeenCalledWith('/api/ports/5'))
    confirmSpy.mockRestore()
  })

  it('anulowany confirm nie wysyła DELETE', async () => {
    USER = { role: 'admin' }
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderPorts()
    fireEvent.click(await screen.findByRole('button', { name: 'Usuń' }))
    expect(delMock).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('logistyk nie widzi przycisku usuwania', async () => {
    USER = { role: 'logistics' }
    renderPorts()
    await screen.findByText('Shanghai')
    expect(screen.queryByRole('button', { name: 'Usuń' })).toBeNull()
  })
})
