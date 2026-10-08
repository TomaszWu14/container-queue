// @vitest-environment jsdom
// „Moje awizacje”: spedytor z kontem proponuje inny termin (POST /api/avizo-forwarder/{id}/propose)
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../api', () => ({
  api: { get: apiGet, post: apiPost }, errorMessage: (e: unknown) => String(e),
}))
vi.mock('../feedback', async (orig) => ({
  ...(await orig() as object), useToast: () => ({ showToast: vi.fn() }),
}))

import MyAvizosPage from './MyAvizosPage'

afterEach(() => { cleanup(); apiGet.mockReset(); apiPost.mockReset() })

describe('MyAvizosPage — propozycja terminu', () => {
  it('wysyła kontener, datę, godzinę i uwagę', async () => {
    apiGet.mockResolvedValue([{ id: 8, status: 'APPROVED_BY_US', stage: 0, company: 'ACME',
      forwarder: 'SPEDALFA', created_at: '2026-10-07T08:00:00',
      items: [{ container_id: 3, container_no: 'MSDU0806613' }] }])
    apiPost.mockResolvedValue({ ok: true })
    const { container } = render(<MemoryRouter><MyAvizosPage /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Zaproponuj inny termin' }))
    fireEvent.change(container.querySelector('input[type=date]')!, { target: { value: '2026-10-20' } })
    fireEvent.change(container.querySelector('input[type=time]')!, { target: { value: '09:00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Wyślij propozycję' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/avizo-forwarder/8/propose',
      { container_id: 3, date: '2026-10-20', time: '09:00', note: '' }))
  })
})
