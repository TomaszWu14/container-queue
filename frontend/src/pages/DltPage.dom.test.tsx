// @vitest-environment jsdom
// Publiczna strona DLT (/dlt/:token): render aut i pozycji (HU/ilości),
// sekwencja przycisków Przygotowane -> Wysłane, stan po realizacji i 404.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../api', () => ({
  api: { get: apiGet, post: apiPost },
  ApiError: class ApiError extends Error {
    status: number
    constructor(status: number) { super(`HTTP ${status}`); this.status = status }
  },
  errorMessage: (e: unknown) => String(e),
}))

import DltPage from './DltPage'

afterEach(() => { cleanup(); apiGet.mockReset(); apiPost.mockReset() })

const info = (status = 'sent') => ({
  number: 'PC-2026-0001', status, needed_by: '2026-09-25', notes: '',
  trucks: [{ ordinal: 1, capacity: 33, lines: [
    { produkt: 'DEMO-SKU-X', krotki_opis: 'Opatrunki', ilosc_pal: 5,
      pallets: 4.5, hu_numbers: 'HU001,HU002', data_dostawy: null },
  ] }],
  unassigned_lines: [],
})

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/dlt/tok123']}>
      <Routes><Route path="/dlt/:token" element={<DltPage />} /></Routes>
    </MemoryRouter>)
}

describe('DltPage', () => {
  it('renderuje wywołanie: numer, auto, pozycje z HU i paletami', async () => {
    apiGet.mockResolvedValue(info())
    renderPage()
    await screen.findByText(/PC-2026-0001/)
    expect(screen.getByText(/DEMO-SKU-X/)).toBeTruthy()
    expect(screen.getByText('HU001,HU002')).toBeTruthy()
    expect(screen.getByText('4.5')).toBeTruthy()
    // sekwencja: Wysłane zablokowane przed Przygotowane
    const shippedBtn = screen.getByRole('button', { name: /Wysłane/ })
    expect((shippedBtn as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByRole('button', { name: /Przygotowane/ })).toBeTruthy()
  })

  it('Przygotowane odblokowuje Wysłane; Wysłane kończy stronę', async () => {
    apiGet.mockResolvedValue(info())
    apiPost.mockResolvedValue({ status: 'ok' })
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /Przygotowane/ }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/dlt/tok123/prepared', {}))
    const shippedBtn = screen.getByRole('button', { name: /Wysłane/ })
    await waitFor(() => expect((shippedBtn as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(shippedBtn)
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/dlt/tok123/shipped', {}))
    await screen.findByText(/Potwierdzono wysyłkę/)
    expect(screen.queryByRole('button', { name: /Wysłane/ })).toBeNull()
  })

  it('status przygotowane z API: od razu tylko Wysłane aktywne', async () => {
    apiGet.mockResolvedValue(info('przygotowane'))
    renderPage()
    const shippedBtn = await screen.findByRole('button', { name: /Wysłane/ })
    expect((shippedBtn as HTMLButtonElement).disabled).toBe(false)
    expect(screen.queryByRole('button', { name: /Przygotowane/ })).toBeNull()
  })

  it('404 = link wygasł (jednolity komunikat)', async () => {
    const { ApiError } = await import('../api')
    apiGet.mockRejectedValue(new (ApiError as never as { new(s: number): Error })(404))
    renderPage()
    await screen.findByText(/Link wygasł|wygasł/)
  })
})
