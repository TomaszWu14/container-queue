// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AvizoDriverFormPage, { driverError } from './AvizoDriverFormPage'

vi.mock('../i18n', () => ({ useT: () => (key: string) => key }))

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const res = (status: number, body: unknown = {}) =>
  ({ ok: status < 300, status, json: async () => body })
const DATA = { stage: 2, language: 'pl', forwarder: 'FW', company: 'ACME', note: '',
  items: [{ container_id: 7, container_no: 'MSCU1234571', vessel: '', notify_date: '2026-10-05',
            warehouse: 'DLT', slot_time: '09:00' }] }

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/avizo/driver/tok2']}>
      <Routes><Route path="/avizo/driver/:token" element={<AvizoDriverFormPage />} /></Routes>
    </MemoryRouter>,
  )
}

describe('driverError — lustro walidacji backendu', () => {
  it.each([
    ['driver_phone', '+48 600 100 200', ''], ['driver_phone', '600100200', ''],
    ['driver_phone', '0048600100200', ''], ['driver_phone', '600-abc', 'av2ErrPhone'],
    ['driver_phone', '12345', 'av2ErrPhone'],
    ['truck_no', 'wx 1234a', ''], ['truck_no', 'AB1', 'av2ErrPlate'],
    ['truck_no', 'ABC_123', 'av2ErrPlate'], ['trailer_no', '', ''],
    ['trailer_no', 'WX12345678901', 'av2ErrPlate'], ['driver_name', 'J', 'av2ErrName'],
    ['driver_id_no', '', ''],
  ] as const)('%s=%s → %s', (field, value, expected) => {
    expect(driverError(field, value)).toBe(expected)
  })
})

describe('AvizoDriverFormPage', () => {
  it('walidacja blokuje wysyłkę; poprawne dane → POST JSON → stan wysłany', async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST' ? res(200, { ok: true, total: 1 }) : res(200, DATA))
    vi.stubGlobal('fetch', fetchMock)
    renderPage()
    expect(await screen.findByText('MSCU1234571')).toBeTruthy()
    expect(screen.getByText('av2RodoTitle')).toBeTruthy()
    const phone = screen.getByLabelText('driverPhone') as HTMLInputElement
    expect(phone.inputMode).toBe('tel')

    fireEvent.click(screen.getByText('av2Submit'))
    expect(await screen.findByText('av2ErrName')).toBeTruthy()
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === 'POST')).toBe(false)

    fireEvent.change(screen.getByLabelText(/^driverName/), { target: { value: 'Jan Kowalski' } })
    fireEvent.change(phone, { target: { value: '600 100 200' } })
    fireEvent.change(screen.getByLabelText(/^truckNo/), { target: { value: 'WX1234A' } })
    fireEvent.click(screen.getByText('av2Submit'))
    expect(await screen.findByText(/av1Done$/)).toBeTruthy()
    const [url, init] = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')!
    expect(url).toBe('/api/avizo/driver/tok2')
    expect((init!.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(JSON.parse(String(init!.body)).items[0]).toEqual({ container_id: 7,
      driver_name: 'Jan Kowalski', driver_phone: '600 100 200', truck_no: 'WX1234A',
      trailer_no: '', driver_id_no: '' })
  })

  it('409 przy GET → już wysłany; 410 → wygasł', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res(409)))
    renderPage()
    expect(await screen.findByText(/av1Done$/)).toBeTruthy()
    cleanup()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res(410)))
    renderPage()
    await waitFor(() => expect(screen.getByText('avizoNotFound')).toBeTruthy())
  })
})
