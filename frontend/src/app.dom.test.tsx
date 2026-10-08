// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

// Lekki użytkownik z dostępem do dashboardu (dokładny kształt nie jest istotny dla routingu).
const USER = { id: 1, login: 'admin', role: 'admin', full_name: 'Admin',
  must_change_password: false, view_all_companies: true }

// Mock API: /api/auth/me zwraca zalogowanego usera; reszta zapytań (sidebar, dashboard) → puste.
vi.mock('./api', () => ({
  api: { get: (path: string) => Promise.resolve(path.includes('/auth/me') ? USER : []),
    put: () => Promise.resolve({}) },
  logoutRequest: () => Promise.resolve(),
  ApiError: class extends Error {},
  errorMessage: (e: unknown) => String(e),
}))
// DashboardPage odpala własne zapytania — podmieniamy na stub, żeby test był stabilny.
vi.mock('./pages/DashboardPage', () => ({ default: () => <div>DASHBOARD</div> }))
vi.mock('./pages/QueuePage', () => ({ default: () => <div>STUB-KOLEJKA</div> }))
vi.mock('./pages/LoginPage', () => ({ default: () => <div>LOGOWANIE</div> }))

afterEach(cleanup)

function mountAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
}
// App importujemy po zarejestrowaniu mocków.
import App from './App'

describe('App — zalogowany na trasie tylko-dla-gościa', () => {
  it('regresja: /login po zalogowaniu → redirect na dashboard, nie 404', async () => {
    mountAt('/login')
    // timeout 5s: pod pełną, równoległą suitą domyślne 1s potrafi nie zdążyć (flake)
    await waitFor(() => expect(screen.getByText('DASHBOARD')).toBeTruthy(), { timeout: 5000 })
    // 404 („nie znaleziono") nie może się pojawić na /login dla zalogowanego usera.
    expect(screen.queryByText(/nie znaleziono/i)).toBeNull()
  })

  it('nieznana trasa dalej daje 404 dla zalogowanego', async () => {
    mountAt('/taka-trasa-nie-istnieje')
    await waitFor(() => expect(screen.queryByText(/nie znaleziono/i)).not.toBeNull(), { timeout: 5000 })
  })
})

describe('App — usunięta zakładka „Co dziś” (/dzis)', () => {
  it('/dzis → przekierowanie na /kolejka (z zachowaniem query), bez linku /dzis w menu', async () => {
    const { container } = mountAt('/dzis?firm=acme')
    await waitFor(() => expect(screen.getByText('STUB-KOLEJKA')).toBeTruthy(), { timeout: 5000 })
    expect(container.querySelector('a[href="/dzis"]')).toBeNull()
    expect(container.querySelector('a[href="/kolejka"]')).toBeTruthy()
  })
})

// sonda adresu — sprawdza, dokąd App nawigował
function Loc() { return <output data-testid="loc">{useLocation().pathname}</output> }

describe('App — wylogowanie i wygaśnięcie sesji', () => {
  it('regresja: po wylogowaniu adres wraca na „/” (wspólny terminal)', async () => {
    const { container } = render(<MemoryRouter initialEntries={['/kolejka']}><App /><Loc /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('STUB-KOLEJKA')).toBeTruthy(), { timeout: 5000 })
    fireEvent.click(container.querySelector('.tn-logout-item')!)
    await waitFor(() => expect(screen.getByText('LOGOWANIE')).toBeTruthy(), { timeout: 5000 })
    expect(screen.getByTestId('loc').textContent).toBe('/')
  })

  it('zdarzenie sesja-wygasła → ekran logowania pod tym samym adresem', async () => {
    render(<MemoryRouter initialEntries={['/kolejka']}><App /><Loc /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('STUB-KOLEJKA')).toBeTruthy(), { timeout: 5000 })
    act(() => { window.dispatchEvent(new Event('timporye:session-expired')) })
    await waitFor(() => expect(screen.getByText('LOGOWANIE')).toBeTruthy(), { timeout: 5000 })
    expect(screen.queryByText('STUB-KOLEJKA')).toBeNull()
    expect(screen.getByTestId('loc').textContent).toBe('/kolejka')
  })
})
