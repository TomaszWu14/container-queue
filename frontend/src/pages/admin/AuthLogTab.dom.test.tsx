// @vitest-environment jsdom
// Strażnik audytu 2026-09-23: log autoryzacji ładuje się na „Filtruj", nie na każdy znak;
// spóźniona odpowiedź nie nadpisuje nowszej; udane ładowanie czyści błąd.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
interface Deferred { resolve: (v: unknown) => void; reject: (e: unknown) => void }
let pending: Deferred[] = []
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
apiGet.mockImplementation((path: string) => path.startsWith('/api/admin/blocked-ips')
  ? Promise.resolve([])
  : new Promise((resolve, reject) => { pending.push({ resolve, reject }) }))
vi.mock('../../api', () => ({
  api: { get: apiGet },
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

import AuthLogTab from './AuthLogTab'

afterEach(() => { cleanup(); pending = []; apiGet.mockClear() })

const logCalls = () => apiGet.mock.calls.filter(c => String(c[0]).startsWith('/api/admin/auth-log'))
const entry = (login: string) => [{ id: 1, field: 'login_fail', login, note: '', created_at: '2026-09-23T10:00:00' }]

describe('AuthLogTab', () => {
  it('pisanie w filtrze nie wysyła żądań; „Filtruj" wysyła jedno z aktualną frazą', async () => {
    render(<AuthLogTab />)
    const q = screen.getByPlaceholderText('authLogAccount')
    for (const v of ['a', 'ad', 'adm', 'admi', 'admin']) fireEvent.change(q, { target: { value: v } })
    expect(logCalls()).toHaveLength(1)                     // tylko start
    fireEvent.click(screen.getByText('authLogFilter'))
    expect(logCalls()).toHaveLength(2)
    expect(logCalls()[1][0]).toContain('q=admin')
  })

  it('starsza odpowiedź nie nadpisuje nowszej, a sukces czyści błąd', async () => {
    render(<AuthLogTab />)
    await act(async () => { pending[0].reject(new Error('Błąd 500')) })
    expect(await screen.findByText('Błąd 500')).toBeTruthy()
    fireEvent.change(screen.getByPlaceholderText('authLogAccount'), { target: { value: 'adm' } })
    fireEvent.click(screen.getByText('authLogFilter'))
    fireEvent.change(screen.getByPlaceholderText('authLogAccount'), { target: { value: 'admin' } })
    fireEvent.click(screen.getByText('authLogFilter'))
    await waitFor(() => expect(pending).toHaveLength(3))
    await act(async () => { pending[2].resolve(entry('NOWY')) })
    await screen.findByText('NOWY')
    await act(async () => { pending[1].resolve(entry('STARY')) })
    expect(screen.queryByText('STARY')).toBeNull()
    expect(screen.queryByText('Błąd 500')).toBeNull()
  })
})
