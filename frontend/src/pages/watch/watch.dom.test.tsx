// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(() => Promise.resolve({ watching: true })),
}))
vi.mock('../../api', () => ({ api: { get: apiGet, post: apiPost } }))
vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../../dates', () => ({ formatDateTime: (s: string) => `D:${s}` }))

import WatchReasonDialog from './WatchReasonDialog'
import WatchersPanel from './WatchersPanel'

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('WatchReasonDialog', () => {
  it('szybki powód wypełnia pole i „Obserwuj" oddaje tekst', () => {
    const onConfirm = vi.fn()
    render(<WatchReasonDialog onConfirm={onConfirm} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'watchReasonDelay' }))
    fireEvent.click(screen.getByRole('button', { name: 'watchConfirm' }))
    expect(onConfirm).toHaveBeenCalledWith('watchReasonDelay')
  })

  it('„Pomiń powód" oddaje pusty powód', () => {
    const onConfirm = vi.fn()
    render(<WatchReasonDialog onConfirm={onConfirm} onClose={() => {}} />)
    fireEvent.change(screen.getByLabelText('watchReasonOther'), { target: { value: 'coś' } })
    fireEvent.click(screen.getByRole('button', { name: 'watchSkipReason' }))
    expect(onConfirm).toHaveBeenCalledWith('')
  })
})

describe('WatchersPanel', () => {
  it('odpowiedź bez listy watchers (np. mock innej strony) — panel się nie wywraca, nic nie rysuje', async () => {
    apiGet.mockResolvedValue({ id: 5, container_no: 'X' })
    const { container } = render(<WatchersPanel baseUrl="/api/containers/5" />)
    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    await new Promise(r => setTimeout(r, 0))
    expect(container.innerHTML).toBe('')
  })

  it('pokazuje obserwujących z powodem i datą; dodanie idzie przez okienko powodu', async () => {
    apiGet.mockResolvedValueOnce({ watching: false, watchers: [
      { user_id: 1, name: 'Jan Kowalski', reason: 'Reklamacja', created_at: '2026-09-24T10:00:00', has_avatar: false },
      { user_id: 2, name: 'Ala Nowak', reason: '', created_at: null, has_avatar: false },
    ] }).mockResolvedValue({ watching: true, watchers: [] })
    render(<WatchersPanel baseUrl="/api/containers/5" />)
    expect(await screen.findByText('Jan Kowalski')).toBeTruthy()
    expect(screen.getByText('Reklamacja')).toBeTruthy()
    expect(screen.getByText('D:2026-09-24T10:00:00')).toBeTruthy()
    expect(screen.getByText('JK')).toBeTruthy()          // inicjały

    fireEvent.click(screen.getByRole('button', { name: /watchAdd/ }))
    fireEvent.click(screen.getByRole('button', { name: 'watchReasonUrgent' }))
    fireEvent.click(screen.getByRole('button', { name: 'watchConfirm' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/containers/5/watch', { reason: 'watchReasonUrgent' }))
  })

  it('zdjęcie obserwacji bez okienka', async () => {
    apiGet.mockResolvedValue({ watching: true, watchers: [] })
    render(<WatchersPanel baseUrl="/api/tracking/vessels/3" />)
    fireEvent.click(await screen.findByRole('button', { name: /watchRemove/ }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/tracking/vessels/3/watch', {}))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('nie pokazuje nieaktualnych danych po zmianie baseUrl (spóźniona odpowiedź)', async () => {
    let resolveFirst: (v: unknown) => void = () => {}
    apiGet.mockImplementationOnce(() => new Promise(res => { resolveFirst = res }))
    apiGet.mockResolvedValueOnce({ watching: false, watchers: [
      { user_id: 9, name: 'Nowy Statek', reason: '', created_at: null, has_avatar: false },
    ] })
    const { rerender } = render(<WatchersPanel baseUrl="/api/tracking/vessels/1" />)
    rerender(<WatchersPanel baseUrl="/api/tracking/vessels/2" />)
    expect(await screen.findByText('Nowy Statek')).toBeTruthy()

    // spóźniona odpowiedź dla starego baseUrl nie może nadpisać aktualnych danych
    resolveFirst({ watching: false, watchers: [
      { user_id: 1, name: 'Stary Statek', reason: '', created_at: null, has_avatar: false },
    ] })
    await new Promise(r => setTimeout(r, 0))
    expect(screen.queryByText('Stary Statek')).toBeNull()
    expect(screen.getByText('Nowy Statek')).toBeTruthy()
  })
})
