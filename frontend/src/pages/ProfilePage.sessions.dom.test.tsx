// @vitest-environment jsdom
// Tabela sesji (audyt UI B32/C27 — UX-031, UX-036): każda kolumna ma widoczny nagłówek, bieżąca sesja
// jest pierwsza z czytelnym znacznikiem (success, nie granatowy mono), „Wyloguj wszystkie inne” stoi
// NAD listą i tylko gdy są inne sesje; tabela mieści się w karcie na telefonie (3 kolumny, przewijanie).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'

const { sessions } = vi.hoisted(() => ({ sessions: { current: [] as unknown[] } }))
vi.mock('../api', () => ({
  api: { get: () => Promise.resolve(sessions.current), post: vi.fn(), del: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('../App', () => ({ useUser: () => ({ id: 1, role: 'logistics' }) }))
vi.mock('./profile/AvatarSection', () => ({ default: () => null }))

import ProfilePage from './ProfilePage'

afterEach(cleanup)

const S = (id: number, current = false) =>
  ({ id, created_at: `2026-09-2${id}T10:00:00`, expires_at: '2026-10-12T10:00:00', current })

describe('profil — tabela sesji', () => {
  it('nagłówki widoczne, bieżąca sesja pierwsza ze znacznikiem, „Wyloguj wszystkie inne” nad tabelą', async () => {
    sessions.current = [S(1), S(2, true), S(3)]
    render(<ProfilePage />)
    const badge = await screen.findByText('ta sesja')
    const table = badge.closest('table')!
    const heads = [...table.querySelectorAll('thead th')]
    expect(heads.map(h => h.textContent)).toEqual(['Utworzona', 'Wygasa', 'Akcje'])
    for (const h of heads) expect(h.querySelector('.sr-only')).toBeNull()
    const rows = table.querySelectorAll('tbody tr')
    expect(within(rows[0] as HTMLElement).queryByText('ta sesja')).not.toBeNull()
    expect(badge.className).toContain('sess-current')
    expect(within(table).getAllByRole('button', { name: 'Wyloguj' })).toHaveLength(2)
    const revokeAll = screen.getByRole('button', { name: 'Wyloguj wszystkie inne' })
    // przycisk przed tabelą w kolejności dokumentu
    expect(revokeAll.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(table.parentElement!.className).toContain('table-scroll')
  })

  it('tylko bieżąca sesja: bez „Wyloguj wszystkie inne”', async () => {
    sessions.current = [S(2, true)]
    render(<ProfilePage />)
    await screen.findByText('ta sesja')
    expect(screen.queryByRole('button', { name: 'Wyloguj wszystkie inne' })).toBeNull()
  })
})
