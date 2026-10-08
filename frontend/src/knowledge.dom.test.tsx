// @vitest-environment jsdom
// Moduł Wiedza (W16): panel 📘 z licznikiem, baner nieprzeczytanych not z ack,
// ranking tematów wg głosów + blokada podwójnego głosu w UI.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const USER = { id: 1, login: 'admin', role: 'admin', full_name: 'Admin',
  must_change_password: false, view_all_companies: true }

const NOTES = [
  { id: 1, scope_type: 'screen', scope_key: 'kolejka', title: 'Jak czytać pilność',
    body: 'Opis...', url: 'https://youtu.be/abc', is_active: true,
    created_at: '2026-09-01T10:00:00', created_by_name: 'Admin' },
  { id: 2, scope_type: 'screen', scope_key: 'kolejka', title: 'Procedura awizacji',
    body: '', url: '', is_active: true,
    created_at: '2026-09-02T10:00:00', created_by_name: 'Admin' },
]
const TOPICS = [
  { id: 1, scope_type: '', scope_key: '', title: 'Najwięcej głosów', body: '',
    status: 'otwarty', created_at: '2026-09-01T10:00:00', created_by_name: 'A',
    votes: 5, my_vote: true },
  { id: 2, scope_type: '', scope_key: '', title: 'Mniej głosów', body: '',
    status: 'otwarty', created_at: '2026-09-02T10:00:00', created_by_name: 'B',
    votes: 1, my_vote: false },
]
const BULLETINS = [
  { id: 7, title: 'Nowa procedura bramy', body: 'Od jutra...', roles: ['admin'],
    created_at: '2026-09-01T10:00:00', created_by_name: 'Admin' },
]

const acked: number[] = []
const posted: string[] = []

vi.mock('./api', () => ({
  api: {
    get: (path: string) => Promise.resolve(
      path.startsWith('/api/knowledge/notes') ? NOTES
        : path.startsWith('/api/knowledge/topics') ? TOPICS
          : path.startsWith('/api/knowledge/bulletins/unread')
            ? BULLETINS.filter(b => !acked.includes(b.id))
            : []),
    post: (path: string) => {
      posted.push(path)
      const ack = path.match(/bulletins\/(\d+)\/ack/)
      if (ack) acked.push(Number(ack[1]))
      if (path.endsWith('/vote')) return Promise.resolve({ ...TOPICS[1], votes: 2, my_vote: true })
      return Promise.resolve({})
    },
    patch: () => Promise.resolve({}),
    del: () => Promise.resolve({}),
  },
  ApiError: class extends Error {},
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => USER }))

import KnowledgePanel from './KnowledgePanel'
import { TopicsTab } from './pages/WiedzaPage'
import { BulletinBanner } from './KnowledgePanel'

afterEach(cleanup)

describe('KnowledgePanel — 📘 z licznikiem i treścią', () => {
  it('pokazuje licznik notek i po kliknięciu treść z linkiem YouTube', async () => {
    render(<KnowledgePanel scopes={[{ scope_type: 'screen', scope_key: 'kolejka' }]} />)
    await waitFor(() => expect(screen.getByText('2')).toBeTruthy())
    fireEvent.click(screen.getByText('2').closest('button')!)
    expect(screen.getByText('Jak czytać pilność')).toBeTruthy()
    // YouTube jako link (bez iframe — CSP)
    const link = screen.getByText(/Obejrzyj wideo/).closest('a')!
    expect(link.getAttribute('href')).toBe('https://youtu.be/abc')
    expect(document.querySelector('iframe')).toBeNull()
    // przycisk zgłoszenia tematu obecny
    expect(screen.getByText(/Zgłoś do omówienia/)).toBeTruthy()
  })
})

describe('KnowledgePanel — ACL-001 bez partnerów zewnętrznych', () => {
  it('spedytor i agencja celna nie widzą panelu wiedzy', () => {
    for (const role of ['forwarder', 'customs'] as const) {
      Object.assign(USER, { role })
      const { container } = render(<KnowledgePanel scopes={[{ scope_type: 'screen', scope_key: 'kolejka' }]} />)
      expect(container.innerHTML).toBe('')
      cleanup()
    }
    Object.assign(USER, { role: 'admin' })
  })
})

describe('TopicsTab — ranking wg głosów', () => {
  it('sortuje wg głosów i blokuje +1 przy oddanym głosie', async () => {
    render(<TopicsTab />)
    await waitFor(() => expect(screen.getByText('Najwięcej głosów')).toBeTruthy())
    const rows = screen.getAllByTestId('kb-topic')
    expect(rows[0].textContent).toContain('Najwięcej głosów')
    expect(rows[1].textContent).toContain('Mniej głosów')
    const voteButtons = rows.map(r => r.querySelector('button')!)
    expect(voteButtons[0].hasAttribute('disabled')).toBe(true)   // my_vote
    expect(voteButtons[1].hasAttribute('disabled')).toBe(false)
  })
})

describe('Wiedza — sprzedaż tylko czyta (backend InternalWriters bez sales)', () => {
  it('sales: „+1” zablokowane, brak „Zgłoś do omówienia” w panelu', async () => {
    Object.assign(USER, { role: 'sales' })
    try {
      render(<TopicsTab />)
      await waitFor(() => expect(screen.getByText('Mniej głosów')).toBeTruthy())
      for (const row of screen.getAllByTestId('kb-topic'))
        expect(row.querySelector('button')!.hasAttribute('disabled')).toBe(true)
      cleanup()
      render(<KnowledgePanel scopes={[{ scope_type: 'screen', scope_key: 'kolejka' }]} />)
      await waitFor(() => expect(screen.getByText('2')).toBeTruthy())
      fireEvent.click(screen.getByText('2').closest('button')!)
      expect(screen.getByText('Jak czytać pilność')).toBeTruthy()
      expect(screen.queryByText(/Zgłoś do omówienia/)).toBeNull()
    } finally { Object.assign(USER, { role: 'admin' }) }
  })
})

describe('TopicsTab — dwuklik „+1”', () => {
  it('regresja: dwa szybkie kliknięcia = jeden POST głosu', async () => {
    posted.length = 0
    render(<TopicsTab />)
    await waitFor(() => expect(screen.getByText('Mniej głosów')).toBeTruthy())
    const btn = screen.getAllByTestId('kb-topic')[1].querySelector('button')!
    fireEvent.click(btn)
    fireEvent.click(btn)
    await waitFor(() => expect(btn.hasAttribute('disabled')).toBe(true))
    expect(posted.filter(p => p.endsWith('/vote'))).toEqual(['/api/knowledge/topics/2/vote'])
  })
})

describe('BulletinBanner — baner nieprzeczytanych not', () => {
  it('pokazuje licznik, a „Przeczytałem" zdejmuje notę z banera', async () => {
    render(<BulletinBanner />)
    await waitFor(() =>
      expect(screen.getByText(/Masz nieprzeczytane noty \(1\)/)).toBeTruthy())
    fireEvent.click(screen.getByText('Pokaż'))
    expect(screen.getByText('Nowa procedura bramy')).toBeTruthy()
    fireEvent.click(screen.getByText(/Przeczytałem/))
    await waitFor(() =>
      expect(screen.queryByText(/Masz nieprzeczytane noty/)).toBeNull())
    expect(acked).toContain(7)
  })
})
