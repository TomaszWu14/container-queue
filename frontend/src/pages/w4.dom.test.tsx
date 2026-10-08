// @vitest-environment jsdom
// W4: matryca reguł powiadomień, dziennik zmian, podświetlenie @wzmianki
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), del: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
import { api } from '../api'
import { ToastProvider } from '../feedback'
import { renderWithMentions } from '../collaboration'
import NotificationRulesTab from './admin/NotificationRulesTab'
import ChangesFeedPage from './ChangesFeedPage'

afterEach(() => { cleanup(); vi.clearAllMocks() })

const wrap = (ui: React.ReactNode) => render(
  <MemoryRouter><ToastProvider>{ui}</ToastProvider></MemoryRouter>)

describe('renderWithMentions', () => {
  it('podświetla @loginy, resztę zostawia tekstem', () => {
    render(<div>{renderWithMentions('Hej @kasia.n, zerknij proszę')}</div>)
    const mention = screen.getByText('@kasia.n')
    expect(mention.className).toBe('mention')
    expect(screen.getByText(/zerknij proszę/)).toBeTruthy()
  })
})

describe('NotificationRulesTab', () => {
  const rules = {
    kinds: ['message', 'demurrage'],
    channels: ['bell', 'email', 'teams'],
    roles: ['admin', 'logistics'],
    rules: [{ kind: 'message', role: 'logistics', channel: 'bell', enabled: false }],
  }

  it('renderuje matrycę i zapisuje wyłączenia', async () => {
    vi.mocked(api.get).mockResolvedValue(rules)
    vi.mocked(api.put).mockResolvedValue({ ok: true })
    wrap(<NotificationRulesTab />)
    await waitFor(() => expect(screen.getByText('message')).toBeTruthy())
    // istniejące nadpisanie: dzwonek dla message/logistics odznaczony
    const bell = screen.getByLabelText('message bell') as HTMLInputElement
    expect(bell.checked).toBe(false)
    // wyłącz Teams dla demurrage i zapisz
    fireEvent.click(screen.getByLabelText('demurrage teams'))
    fireEvent.click(screen.getByRole('button', { name: /Zapisz|Save/i }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const sent = vi.mocked(api.put).mock.calls[0][1] as
      { kind: string; role: string; channel: string; enabled: boolean }[]
    expect(sent).toContainEqual(
      { kind: 'demurrage', role: '*', channel: 'teams', enabled: false })
    expect(sent).toContainEqual(
      { kind: 'message', role: 'logistics', channel: 'bell', enabled: false })
  })
})

describe('ChangesFeedPage', () => {
  it('renderuje wpisy dziennika z filtrami i paginacją', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url.startsWith('/api/changes/feed')) {
        return Promise.resolve({
          total: 1, page: 1, per_page: 50,
          entries: [{
            id: 1, at: '2026-09-19T08:00:00', entity_type: 'containers',
            entity_id: 5, container_no: 'TGBU6784203', field: 'status',
            old: 'NOWY', new: 'W_TRANSPORCIE', note: '',
            user_login: 'admin', user_name: 'Administrator',
          }],
          entity_types: ['containers'],
          actors: [{ id: 1, login: 'admin', full_name: 'Administrator' }],
        })
      }
      return Promise.resolve([])
    })
    wrap(<ChangesFeedPage />)
    await waitFor(() => expect(screen.getByText('TGBU6784203')).toBeTruthy())
    expect(screen.getByText('Administrator', { selector: 'td' })).toBeTruthy()
    expect(screen.getByText('1 / 1')).toBeTruthy()
    // filtr użytkownika obecny
    expect(screen.getByText('Wszyscy użytkownicy')).toBeTruthy()
  })
})
