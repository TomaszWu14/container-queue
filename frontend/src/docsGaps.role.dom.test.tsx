// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { DocsGapsCard } from './DocumentsW5'

// S10 (audyt UI): karta braków dokumentów pyta API tylko dla ról z dostępem (z /me),
// zamiast łapać 403 — spedytor widzi swoje kontenery, magazyn/agencja/zakupy nic nie wołają.
vi.mock('./i18n', async (orig) => ({
  ...await orig<typeof import('./i18n')>(), useT: () => (k: string) => k,
}))
const { role } = vi.hoisted(() => ({ role: { v: 'forwarder' } }))
vi.mock('./userContext', () => ({ useUser: () => ({ role: role.v }) }))
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('./api', () => ({ api: { get: apiGet }, downloadFile: vi.fn(), errorMessage: String }))

afterEach(() => { cleanup(); apiGet.mockReset(); role.v = 'forwarder' })

it('logistyka widzi braki dokumentów', async () => {
  role.v = 'logistics'
  apiGet.mockResolvedValue([{ id: 7, container_no: 'MSDU0806613', eta: null, missing: ['CMR'] }])
  render(<MemoryRouter><DocsGapsCard /></MemoryRouter>)
  expect(await screen.findByText('MSDU0806613')).toBeTruthy()
  expect(apiGet).toHaveBeenCalledWith('/api/customs/docs-gaps')
})

// spedytor: bez dostępu do dokumentów odprawowych (decyzja 2026-09-28)
it.each(['forwarder', 'warehouse', 'customs', 'purchasing'])('%s: brak zapytania i brak karty', r => {
  role.v = r
  const { container } = render(<MemoryRouter><DocsGapsCard /></MemoryRouter>)
  expect(apiGet).not.toHaveBeenCalled()
  expect(container.innerHTML).toBe('')
})
