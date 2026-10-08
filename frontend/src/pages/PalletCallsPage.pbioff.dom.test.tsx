// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

// B19 (audyt UI): Power BI wyłączone (503) → jeden polski baner, bez surowej zmiennej
// środowiskowej, bez „Spróbuj ponownie” i bez sekcji inwentaryzacji HU.
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({
  api: { get: apiGet, post: vi.fn(), upload: vi.fn() },
  downloadFile: vi.fn(), errorMessage: (e: unknown) => String((e as Error).message),
}))
vi.mock('../App', () => ({ useUser: () => ({ role: 'logistics' }) }))
vi.mock('../feedback', async (orig) => ({
  ...(await orig() as object), useToast: () => ({ showToast: vi.fn() }),
}))
afterEach(() => { cleanup(); apiGet.mockReset() })

it('503 z analizy → jeden baner zamiast POWERBI_PROVIDER=off', async () => {
  const off = Object.assign(new Error('POWERBI_PROVIDER=off'), { status: 503 })
  apiGet.mockImplementation((path: string) =>
    path.startsWith('/api/pallet-calls/analysis') || path === '/api/pallet-calls/hu-inventory'
      ? Promise.reject(off) : Promise.resolve([]))
  const { default: PalletCallsPage } = await import('./PalletCallsPage')
  render(<PalletCallsPage />)
  expect(await screen.findByText(/Integracja Power BI jest wyłączona/)).toBeTruthy()
  expect(screen.queryByText(/POWERBI_PROVIDER/)).toBeNull()
  expect(screen.queryByRole('button', { name: /Spróbuj ponownie/i })).toBeNull()
  expect(apiGet).not.toHaveBeenCalledWith('/api/pallet-calls/hu-inventory')
})
