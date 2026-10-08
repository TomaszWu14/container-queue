// @vitest-environment jsdom
// Układ „1a": edycja inline w wierszu, filtr Aktywne/Nieaktywne, usuwanie z 409,
// historia wiersza — na zakładce Porty strony Dane podstawowe (rola admin).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { mdAt } from '../mdRoute.testutil'
import MasterDataPage from '../MasterDataPage'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../../App', () => ({ useUser: () => ({ role: 'admin' }) }))

const { apiGet, apiPatch, apiPost, apiDel, toast } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPatch: vi.fn(), apiPost: vi.fn(), apiDel: vi.fn(), toast: vi.fn(),
}))
vi.mock('../../api', () => ({
  api: { get: apiGet, patch: apiPatch, post: apiPost, del: apiDel },
  errorMessage: (e: unknown) => String((e as Error).message),
}))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast: toast }) }))

const ports = [
  { id: 1, name: 'Dalian', country: 'CN', category: 'GLOWNY_CN', transit_time_days: 36,
    transit_time_long_days: 47, is_active: true, monthly_transit: { 7: 40 } },
  { id: 2, name: 'Fuzhou', country: 'CN', category: 'OUT', transit_time_days: 36,
    transit_time_long_days: 46, is_active: false, monthly_transit: {} },
]

function mockApi() {
  apiGet.mockImplementation((url: string) => {
    if (url.startsWith('/api/companies')) return Promise.resolve([])
    if (url.startsWith('/api/suppliers')) return Promise.resolve([])
    if (url.startsWith('/api/ports')) return Promise.resolve(ports)
    if (url.startsWith('/api/audit/ports/1')) return Promise.resolve([
      { id: 9, field: 'transit_time_days', old_value: '35', new_value: '36',
        note: '', user_login: 't.wu', created_at: '2026-06-18T10:00:00Z' }])
    return Promise.reject(new Error('unmocked ' + url))
  })
}

async function openPorts() {
  render(mdAt('porty', <MasterDataPage />))
  await screen.findByText('Dalian')
}

afterEach(() => {
  cleanup()
  apiGet.mockReset(); apiPatch.mockReset(); apiPost.mockReset(); apiDel.mockReset()
  toast.mockReset()
})

describe('EditableTable — porty (układ 1a)', () => {
  it('klik w komórkę wchodzi w edycję, Zapisz woła PATCH z pełnym body', async () => {
    mockApi()
    apiPatch.mockResolvedValue({})
    await openPorts()

    fireEvent.click(screen.getByText('Dalian'))          // klik w komórkę → tryb edycji
    const row = screen.getByDisplayValue('Dalian').closest('tr')!
    fireEvent.change(within(row).getByDisplayValue('36'), { target: { value: '33' } })
    fireEvent.click(within(row).getByText('save'))

    await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(1))
    const [url, body] = apiPatch.mock.calls[0]
    expect(url).toBe('/api/ports/1')
    expect(body).toMatchObject({
      name: 'Dalian', transit_time_days: 33, is_active: true,
      monthly_transit: { 7: 40 },   // profil sezonowy przechodzi bez zmian
    })
  })

  it('Anuluj nie woła PATCH i wychodzi z trybu edycji', async () => {
    mockApi()
    await openPorts()

    fireEvent.click(screen.getByText('Dalian'))
    fireEvent.click(screen.getByText('cancel'))
    expect(apiPatch).not.toHaveBeenCalled()
    expect(screen.queryByDisplayValue('Dalian')).toBeNull()
    expect(screen.getByText('Dalian')).toBeTruthy()
  })

  it('pigułki Aktywne/Nieaktywne filtrują wiersze i pokazują liczniki', async () => {
    mockApi()
    await openPorts()

    fireEvent.click(screen.getByText(/mdActivePill/))
    expect(screen.queryByText('Fuzhou')).toBeNull()
    expect(screen.getByText('Dalian')).toBeTruthy()

    fireEvent.click(screen.getByText(/mdInactivePill/))
    expect(screen.queryByText('Dalian')).toBeNull()
    expect(screen.getByText('Fuzhou')).toBeTruthy()
    expect(screen.getByText('mdInactivePill 1')).toBeTruthy()   // licznik na pigułce
  })

  it('usuwanie: 409 z backendu pokazuje komunikat serwera w toaście', async () => {
    mockApi()
    apiDel.mockRejectedValue(new Error('Nie można usunąć: rekord używany przez 34'))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await openPorts()

    fireEvent.click(within(screen.getByText('Dalian').closest('tr')!).getByTitle('del'))
    await waitFor(() => expect(apiDel).toHaveBeenCalledWith('/api/ports/1'))
    expect(toast).toHaveBeenCalledWith(
      'Nie można usunąć: rekord używany przez 34', 'error')
  })

  it('⟲ pokazuje historię wiersza z /api/audit', async () => {
    mockApi()
    await openPorts()

    fireEvent.click(within(screen.getByText('Dalian').closest('tr')!).getByTitle('mdHistory'))
    await screen.findByText('transit_time_days')
    expect(screen.getByText('t.wu')).toBeTruthy()
    expect(screen.getByText(/35\s*→\s*36/)).toBeTruthy()
  })

  it('+ Dodaj otwiera wiersz na górze, Zapisz woła POST', async () => {
    mockApi()
    apiPost.mockResolvedValue({})
    await openPorts()

    fireEvent.click(screen.getByText('+ mdAddPort'))
    const addRow = document.querySelector('tbody tr.md-edit-row')!
    fireEvent.change(within(addRow as HTMLElement).getAllByRole('textbox')[0],
                     { target: { value: 'Ningbo' } })
    fireEvent.click(within(addRow as HTMLElement).getByText('save'))

    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(1))
    const [url, body] = apiPost.mock.calls[0]
    expect(url).toBe('/api/ports')
    expect(body).toMatchObject({ name: 'Ningbo', country: 'CN', category: 'OUT',
                                 is_active: true, monthly_transit: {} })
  })

  it('cele zapasu (#373): edycja dni woła POST-upsert po material_no', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url.startsWith('/api/companies')) return Promise.resolve([])
      if (url.startsWith('/api/suppliers')) return Promise.resolve([])
      if (url.startsWith('/api/stock-targets')) return Promise.resolve({
        global_days: 14,
        items: [{ id: 5, material_no: '100200', days: 21, updated_at: '2026-09-01T00:00:00Z' }],
      })
      return Promise.reject(new Error('unmocked ' + url))
    })
    apiPost.mockResolvedValue({})
    render(mdAt('cele-zapasu', <MasterDataPage />))
    await screen.findByText('100200')

    fireEvent.click(screen.getByText('100200'))          // wejście w edycję (klik w komórkę)
    const row = document.querySelector('tr.md-edit-row') as HTMLElement
    fireEvent.change(within(row).getByDisplayValue('21'), { target: { value: '30' } })
    fireEvent.click(within(row).getByText('save'))

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/stock-targets', { material_no: '100200', days: 30 }))
  })
})
