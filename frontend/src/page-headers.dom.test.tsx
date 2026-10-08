// @vitest-environment jsdom
// Nagłówki stron (audyt UI B14/B15/C12 — UX-023, UX-024, UX-034): Zamówienia i Wyceny mają widoczny
// tytuł; przy pustej liście wycen nie ma panelu „Wybierz zlecenie z listy.”, a spedytor widzi tekst
// dla siebie (nie instrukcję dla logistyki); pozycja menu grupy („Operacje”) jest aktywna na jej stronie.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { User } from './types'

const { role } = vi.hoisted(() => ({ role: { current: 'admin' } }))
vi.mock('./api', () => ({
  api: { get: () => Promise.resolve([]), post: () => Promise.resolve({}), patch: () => Promise.resolve({}) },
  downloadFile: () => Promise.resolve(),
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ id: 1, role: role.current }) }))
vi.mock('./NotificationsBell', () => ({ default: () => null }))

import OrdersPage from './pages/OrdersPage'
import QuotesPage from './pages/QuotesPage'
import Sidebar from './Sidebar'
import { UserContext } from './userContext'

afterEach(() => { cleanup(); role.current = 'admin' })

const visibleH1 = () => {
  const h1 = document.querySelector('main h1')
  return h1 && !h1.classList.contains('sr-only') ? h1.textContent : null
}

describe('nagłówki stron', () => {
  it('Zamówienia: widoczny tytuł strony', async () => {
    render(<MemoryRouter><OrdersPage /></MemoryRouter>)
    await screen.findByText('Brak zamówień.')
    expect(visibleH1()).toBe('Zamówienia')
  })

  it('Wyceny (logistyka, pusta lista): tytuł z akcjami, bez „Wybierz zlecenie z listy.”', async () => {
    render(<MemoryRouter><QuotesPage /></MemoryRouter>)
    await screen.findByText('Brak zleceń wyceny.')
    expect(visibleH1()).toBe('Wyceny')
    expect(document.querySelector('.page-head-actions')?.textContent).toContain('Eksport CSV')
    expect(screen.queryByText('Wybierz zlecenie z listy.')).toBeNull()
    expect(document.querySelector('.quotes-detail')).toBeNull()
  })

  it('Wyceny (spedytor, pusta lista): tekst dla spedytora, bez instrukcji dla logistyki i bez eksportu', async () => {
    role.current = 'forwarder'
    render(<MemoryRouter><QuotesPage /></MemoryRouter>)
    await screen.findByText('Nie masz zaproszeń do wyceny.')
    expect(visibleH1()).toBe('Wyceny')
    expect(screen.queryByText(/Utwórz zlecenie wyceny z widoku kontenerów/)).toBeNull()
    expect(screen.queryByText('Wybierz zlecenie z listy.')).toBeNull()
    expect(document.querySelector('.page-head-actions')).toBeNull()
  })

  it('menu: grupa z aktywną stroną jest podświetlona (Operacje na /zamowienia)', async () => {
    render(
      <UserContext.Provider value={{ user: { id: 1, login: 'u', full_name: 'U', role: 'admin' } as User, reload: () => {} }}>
        <MemoryRouter initialEntries={['/zamowienia']}><Sidebar onLogout={() => {}} /></MemoryRouter>
      </UserContext.Provider>,
    )
    const ops = screen.getByRole('button', { name: /Operacje/ })
    await waitFor(() => expect(ops.closest('.tn-group')!.classList.contains('has-active')).toBe(true))
    expect(screen.getByRole('button', { name: /Analiza/ }).closest('.tn-group')!.classList.contains('has-active')).toBe(false)
    fireEvent.click(ops)
    expect(document.querySelector('.tn-group.open .tn-drop-link.active')?.textContent).toBe('Zamówienia')
  })
})
