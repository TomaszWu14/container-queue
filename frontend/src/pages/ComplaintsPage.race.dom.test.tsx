// @vitest-environment jsdom
// Strażnik audytu 2026-09-23: /reklamacje i /reklamacje/archiwum to ta sama instancja
// komponentu — spóźniona odpowiedź listy aktywnych nie może trafić pod „Archiwum".
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('./ComplaintsPanel', () => ({ COMPLAINT_STATUS_BADGE: {} }))
interface Deferred { resolve: (v: unknown) => void; reject: (e: unknown) => void }
let pending: Deferred[] = []
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
apiGet.mockImplementation(() => new Promise((resolve, reject) => { pending.push({ resolve, reject }) }))
vi.mock('../api', () => ({
  api: { get: apiGet },
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

import ComplaintsPage from './ComplaintsPage'

afterEach(() => { cleanup(); pending = []; apiGet.mockClear() })

const list = (no: string, status = 'NOWA') => [{ id: 1, number: no, container_no: 'C1', status,
  problems: [], photo_count: 0, age_days: 1, created_by_login: 'x' }]

describe('ComplaintsPage — lista vs archiwum', () => {
  it('spóźniona odpowiedź aktywnych nie nadpisuje archiwum', async () => {
    const { rerender } = render(<MemoryRouter><ComplaintsPage /></MemoryRouter>)
    rerender(<MemoryRouter><ComplaintsPage archive /></MemoryRouter>)
    await waitFor(() => expect(pending).toHaveLength(2))
    await act(async () => { pending[1].resolve(list('ARCH-1')) })
    expect((await screen.findAllByText('ARCH-1')).length).toBeGreaterThan(0)
    await act(async () => { pending[0].resolve(list('AKT-1')) })
    expect(screen.queryAllByText('AKT-1')).toHaveLength(0)
  })

  it('błąd spóźnionego żądania nie pokazuje się w archiwum', async () => {
    const { rerender } = render(<MemoryRouter><ComplaintsPage /></MemoryRouter>)
    rerender(<MemoryRouter><ComplaintsPage archive /></MemoryRouter>)
    await waitFor(() => expect(pending).toHaveLength(2))
    await act(async () => { pending[1].resolve(list('ARCH-1')) })
    await act(async () => { pending[0].reject(new Error('STARY-BLAD')) })
    expect(screen.queryByText('STARY-BLAD')).toBeNull()
    expect(screen.queryAllByText('ARCH-1').length).toBeGreaterThan(0)
  })

  it('filtr zakładki z aktywnych nie ukrywa archiwum (zakładki tam niewidoczne)', async () => {
    const { rerender } = render(<MemoryRouter><ComplaintsPage /></MemoryRouter>)
    await act(async () => { pending[0].resolve(list('AKT-1')) })
    fireEvent.click(screen.getByRole('button', { name: /cst_NOWA/ }))
    rerender(<MemoryRouter><ComplaintsPage archive /></MemoryRouter>)
    await waitFor(() => expect(pending).toHaveLength(2))
    await act(async () => { pending[1].resolve(list('ARCH-1', 'ZAMKNIETA')) })
    expect(screen.queryAllByText('ARCH-1').length).toBeGreaterThan(0)
  })

  it('po przejściu do archiwum lista aktywnych znika od razu (przed odpowiedzią)', async () => {
    const { rerender } = render(<MemoryRouter><ComplaintsPage /></MemoryRouter>)
    await act(async () => { pending[0].resolve(list('AKT-1')) })
    rerender(<MemoryRouter><ComplaintsPage archive /></MemoryRouter>)
    expect(screen.queryAllByText('AKT-1')).toHaveLength(0)
  })
})
