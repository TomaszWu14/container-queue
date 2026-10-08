// @vitest-environment jsdom
// Strażnik testu akceptacyjnego T1 (2026-09-24): edycja magazynu zmienia limit dzienny,
// „Anuluj" porzuca edycję bez zapisu, a formularz dodawania da się wyczyścić.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
const { apiGet, apiPatch } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPatch: vi.fn() }))
vi.mock('../../api', () => ({
  api: { get: apiGet, patch: apiPatch, post: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./shared', async (orig) => ({ ...(await orig<object>()), useCompanies: () => [] }))

import WarehousesTab from './WarehousesTab'

const WH = { id: 5, name: 'Donnesmarcka 1', company_id: 1, country: 'PL', default_daily_limit: 7,
  email: 'mag@x.pl', slot_windows: '', slot_capacity: 1 }
apiGet.mockResolvedValue([WH])
apiPatch.mockResolvedValue({})

afterEach(() => { cleanup(); apiPatch.mockClear() })

describe('WarehousesTab', () => {
  it('edycja wysyła nowy limit dzienny', async () => {
    render(<WarehousesTab />)
    fireEvent.click(await screen.findByText('edit'))
    fireEvent.change(screen.getByLabelText('dailyLimit'), { target: { value: '3' } })
    fireEvent.click(screen.getByText('save'))
    await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(1))
    expect(apiPatch.mock.calls[0][1]).toMatchObject({ default_daily_limit: 3, email: 'mag@x.pl' })
  })

  it('„Anuluj" w edycji wraca do widoku bez zapisu', async () => {
    render(<WarehousesTab />)
    fireEvent.click(await screen.findByText('edit'))
    fireEvent.click(screen.getByText('cancel'))
    expect(screen.getByText('edit')).toBeTruthy()
    expect(apiPatch).not.toHaveBeenCalled()
  })

  it('„Anuluj" przy dodawaniu pojawia się po wpisaniu i czyści formularz', async () => {
    render(<WarehousesTab />)
    await screen.findByText('edit')
    expect(screen.queryByText('cancel')).toBeNull()
    const name = screen.getByPlaceholderText('name') as HTMLInputElement
    fireEvent.change(name, { target: { value: 'Nowy' } })
    fireEvent.click(screen.getByText('cancel'))
    expect(name.value).toBe('')
    expect(screen.queryByText('cancel')).toBeNull()
  })
})
