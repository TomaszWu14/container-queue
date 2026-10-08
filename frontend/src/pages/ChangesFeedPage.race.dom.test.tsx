// @vitest-environment jsdom
// Strażnik audytu 2026-09-23: spóźniona odpowiedź dla starego filtra spółki
// nie nadpisuje listy dla nowego filtra.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('./admin/shared', () => ({
  useCompanies: () => [{ id: 1, name: 'A' }, { id: 2, name: 'B' }],
  useWarehouses: () => [],
}))
interface Deferred { resolve: (v: unknown) => void; reject: (e: unknown) => void }
let pending: Deferred[] = []
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
apiGet.mockImplementation(() => new Promise((resolve, reject) => { pending.push({ resolve, reject }) }))
vi.mock('../api', () => ({
  api: { get: apiGet },
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

import ChangesFeedPage from './ChangesFeedPage'

afterEach(() => { cleanup(); pending = []; apiGet.mockClear() })

const feed = (note: string) => ({
  total: 1, page: 1, per_page: 50, entity_types: [], actors: [],
  entries: [{ id: 1, at: '2026-09-23T10:00:00', entity_type: 'Container', entity_id: 1,
    container_no: null, field: 'status', old: null, new: null, note, user_login: null,
    user_name: 'x' }],
})

describe('ChangesFeedPage — wyścig filtra', () => {
  it('starsza odpowiedź (spółka A) nie nadpisuje nowszej (spółka B)', async () => {
    render(<MemoryRouter><ChangesFeedPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('company'), { target: { value: '2' } })
    await waitFor(() => expect(pending).toHaveLength(2))
    await act(async () => { pending[1].resolve(feed('NOTKA-B')) })
    await screen.findByText('NOTKA-B')
    await act(async () => { pending[0].resolve(feed('NOTKA-A')) })
    expect(screen.queryByText('NOTKA-A')).toBeNull()
    expect(screen.getByText('NOTKA-B')).toBeTruthy()
  })

  it('błąd starszego żądania nie pokazuje się przy nowym filtrze', async () => {
    render(<MemoryRouter><ChangesFeedPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('company'), { target: { value: '2' } })
    await waitFor(() => expect(pending).toHaveLength(2))
    await act(async () => { pending[1].resolve(feed('NOTKA-B')) })
    await act(async () => { pending[0].reject(new Error('STARY-BLAD')) })
    expect(screen.queryByText('STARY-BLAD')).toBeNull()
  })
})
