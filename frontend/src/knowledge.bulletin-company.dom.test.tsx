// @vitest-environment jsdom
// Noty eskalacyjne (#980): konto grupowe (admin / view_all) wybiera spółkę noty albo „Cała grupa”;
// logistyk jednej spółki nie widzi wyboru (backend i tak przypisuje jego spółkę).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const { user, apiPost } = vi.hoisted(() => ({
  user: { current: { id: 1, role: 'admin', view_all_companies: false } as Record<string, unknown> },
  apiPost: vi.fn((_path: string, _body: unknown) => Promise.resolve({})),
}))
const COMPANIES = [{ id: 1, name: 'ACME', code: 'Z', is_active: true },
                   { id: 2, name: 'DLT', code: 'L', is_active: true }]
const BULLETINS = [
  { id: 7, title: 'Nota grupowa', body: '', roles: ['admin'], company_id: null,
    created_at: '2026-09-01T10:00:00', created_by_name: 'Admin' },
  { id: 8, title: 'Nota DLT', body: '', roles: ['admin'], company_id: 2,
    created_at: '2026-09-02T10:00:00', created_by_name: 'Admin' },
]

vi.mock('./api', () => ({
  api: {
    get: (path: string) => Promise.resolve(path === '/api/companies' ? COMPANIES : BULLETINS),
    post: apiPost,
  },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => user.current }))

import { BulletinsTab } from './pages/WiedzaPage'

afterEach(() => { cleanup(); apiPost.mockClear() })

describe('nota eskalacyjna — wybór spółki', () => {
  it('admin: wybiera spółkę, POST niesie company_id; lista pokazuje plakietki spółek', async () => {
    user.current = { id: 1, role: 'admin', view_all_companies: false }
    render(<BulletinsTab />)
    expect(await screen.findByText('DLT')).toBeTruthy()
    expect(screen.getByText('Cała grupa')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Nowa nota/ }))
    fireEvent.change(screen.getByLabelText('Tytuł'), { target: { value: 'Brama' } })
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    fireEvent.change(screen.getByLabelText('Spółka noty'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Wyślij' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    expect(apiPost.mock.calls[0][1]).toMatchObject({ title: 'Brama', company_id: 2 })
  })

  it('logistyk bez view_all: brak wyboru spółki', async () => {
    user.current = { id: 2, role: 'logistics', view_all_companies: false }
    render(<BulletinsTab />)
    await screen.findByText('Nota DLT')
    fireEvent.click(screen.getByRole('button', { name: /Nowa nota/ }))
    expect(screen.queryByLabelText('Spółka noty')).toBeNull()
  })
})
