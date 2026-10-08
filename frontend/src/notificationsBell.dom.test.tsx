// @vitest-environment jsdom
// Dzwonek → Aktualności (spec 2026-10-01): klik w wiadomość otwiera ją w panelu na Pulpicie,
// „Zobacz wszystkie” prowadzi do sekcji; rola bez Pulpitu — jak dawniej do kontenera.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

vi.mock('./i18n', () => ({ useT: () => (key: string) => key }))
const role = { value: 'admin' }
vi.mock('./App', () => ({ useUser: () => ({ role: role.value }) }))
vi.mock('./routing', () => ({ canAccess: (r: string) => r !== 'warehouse' }))
vi.mock('./pages/news/NewsFeed', () => ({ NEWS_CHANGED: 'news:changed' }))
const get = vi.fn()
const post = vi.fn()
vi.mock('./api', () => ({ api: { get: (p: string) => get(p), post: (p: string, b: unknown) => post(p, b) } }))

import NotificationsBell from './NotificationsBell'

function Where() {
  const loc = useLocation()
  return <output data-testid="where">{loc.pathname + loc.search + loc.hash}</output>
}

const mount = () => {
  get.mockImplementation((p: string) => Promise.resolve(p.includes('unread-count') ? { count: 1 }
    : [{ id: 7, kind: 'customs', title: 'Odprawa zlecona', body: '', container_id: 3, is_read: false, created_at: '2026-10-01T08:00:00' }]))
  post.mockResolvedValue({ ok: true })
  return render(<MemoryRouter initialEntries={['/kolejka']}>
    <NotificationsBell /><Routes><Route path="*" element={<Where />} /></Routes>
  </MemoryRouter>)
}

afterEach(() => { cleanup(); vi.clearAllMocks(); role.value = 'admin' })

describe('NotificationsBell', () => {
  it('klik w wiadomość → Pulpit z otwartą wiadomością', async () => {
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'notifications' }))
    fireEvent.click(await screen.findByText('Odprawa zlecona'))
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/pulpit?wiadomosc=7'))
  })

  it('„Zobacz wszystkie” → sekcja Aktualności', async () => {
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'notifications' }))
    fireEvent.click(await screen.findByText('newsSeeAll'))
    expect(screen.getByTestId('where').textContent).toBe('/pulpit#aktualnosci')
  })

  it('rola bez Pulpitu: klik prowadzi do kontenera, bez „Zobacz wszystkie”', async () => {
    role.value = 'warehouse'
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'notifications' }))
    fireEvent.click(await screen.findByText('Odprawa zlecona'))
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/kontenery/3'))
    expect(screen.queryByText('newsSeeAll')).toBeNull()
  })
})
