// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AnalitykaPage from './pages/AnalitykaPage'

// KPI przy montowaniu: bez podmiany API odpowiedź (błąd sieci) dochodziła po zamknięciu jsdom
// i React planował render bez `window` („window is not defined” w CI z pool: threads)
const get = vi.fn((_path: string) => Promise.resolve(null))
vi.mock('./api', async orig => ({
  ...(await orig<typeof import('./api')>()),
  api: { get: (path: string) => get(path), upload: vi.fn() },
}))

afterEach(cleanup)

describe('AnalitykaPage', () => {
  it('renderuje sekcję wgrywania', async () => {
    render(<AnalitykaPage />)
    expect(screen.getByText(/wgraj/i)).toBeTruthy()
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/analytics/operational'))
  })
})
