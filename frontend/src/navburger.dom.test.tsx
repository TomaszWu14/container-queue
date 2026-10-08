// @vitest-environment jsdom
// audyt UI PR 7b: hamburger otwiera panel menu (klasa na pasku + aria-expanded), Esc zamyka
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('./api', () => ({
  api: { get: (path: string) => Promise.resolve(path.includes('/auth/me')
    ? { id: 1, login: 'u', role: 'admin', full_name: 'U', must_change_password: false } : []) },
  logoutRequest: () => Promise.resolve(),
  ApiError: class extends Error {},
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./pages/DashboardPage', () => ({ default: () => <div>DASHBOARD</div> }))

afterEach(cleanup)

import App from './App'

describe('nawigacja mobilna — hamburger', () => {
  it('przełącza panel menu i zamyka się Escape', async () => {
    render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>)
    const burger = await screen.findByRole('button', { name: 'Otwórz menu' }, { timeout: 10000 })
    expect(burger.getAttribute('aria-controls')).toBe('tn-menu')
    expect(burger.getAttribute('aria-expanded')).toBe('false')
    // zmiana trasy zamyka menu (celowo) — klikamy dopiero po ustaleniu się strony startowej,
    // inaczej spóźnione przejście „/” → pulpit pod obciążeniem zamykało panel
    await screen.findByText('DASHBOARD', undefined, { timeout: 10000 })
    fireEvent.click(burger)
    await waitFor(() => expect(document.querySelector('.topnav')!.classList.contains('mobile-open')).toBe(true))
    expect(screen.getByRole('button', { name: 'Zamknij menu' }).getAttribute('aria-expanded')).toBe('true')
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(document.querySelector('.topnav')!.classList.contains('mobile-open')).toBe(false), { timeout: 5000 })
  })
})
