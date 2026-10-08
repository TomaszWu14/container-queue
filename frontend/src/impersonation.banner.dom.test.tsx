// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// /api/auth/me z impersonated:true — reszta endpointów zwraca puste dane
const user = () => ({ id: 1, login: 'u', role: 'logistics', full_name: 'U',
  must_change_password: false, view_all_companies: false, impersonated: true })

vi.mock('./api', () => ({
  api: {
    get: (path: string) => Promise.resolve(path.includes('/auth/me') ? user() : []),
    post: () => Promise.resolve({}),
    patch: () => Promise.resolve({}),
  },
  logoutRequest: () => Promise.resolve(),
  ApiError: class extends Error {},
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./pages/DashboardPage', () => ({ default: () => <div>DASHBOARD</div> }))

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

import App from './App'

describe('Baner impersonacji', () => {
  it('impersonated:true → baner widoczny, wyjście woła /api/auth/refresh', async () => {
    const fetchSpy = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchSpy)
    render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>)

    const banner = await screen.findByTestId('impersonation-banner', {}, { timeout: 5000 })
    expect(banner.textContent).toContain('Podgląd jako')
    expect(banner.textContent).toContain('tylko odczyt')

    fireEvent.click(screen.getByRole('button', { name: 'Wyjdź z podglądu' }))
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith(
      '/api/auth/refresh', { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } }))
  })
})
