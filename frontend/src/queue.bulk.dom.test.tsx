// @vitest-environment jsdom
// Kolejka Enterprise (plaster 3): pasek akcji masowych zastępuje pasek filtrów przy
// zaznaczeniu; akcje per rola; status/magazyn jednym żądaniem POST /containers/bulk/*.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const USER = { id: 1, login: 'admin', role: 'admin', full_name: 'Admin',
  must_change_password: false, view_all_companies: true }

const base = {
  company_id: 1, company_name: 'Acme', supplier_name: 'Dostawca A', vessel: 'MV DEMO ATLAS',
  eta: '2026-08-01', atd: null, transport_type: 'kola', status: 'W_TRANSPORCIE',
  customs_status: 'BRAK', document_status: 'BRAK', purchasing_status: 'BRAK',
  delivery_note: '', incoming_delivery_no: '18001', purchase_note: '',
  forwarder_name: 'SPEDALFA', document_flow: '', sent_required: null, sent_status: '',
  is_delayed: false, transport_id: null, order_number: null, sent_number: '', order_numbers: '',
}

const CONTAINERS = [
  { ...base, id: 1, container_no: 'CSNU0110266', notify_date: '2026-08-10', warehouse_name: 'ACME' },
  { ...base, id: 2, container_no: 'TIIU9152821', notify_date: '2026-08-11', warehouse_name: 'ACME' },
]
const posts: { path: string; body: unknown }[] = []

vi.mock('./api', () => ({
  api: {
    put: () => Promise.resolve({}),  // setPref → zapis profilu widoku (prefs.ts)
    get: (path: string) => Promise.resolve(
      path.startsWith('/api/containers?') ? CONTAINERS
        : path.startsWith('/api/containers/counts') ? {} : []),
    post: (path: string, body: unknown) => {
      posts.push({ path, body })
      return Promise.resolve(path.includes('/bulk/')
        ? { ok: [1], failed: [{ id: 2, detail: 'Cofnięcie statusu wymaga notatki z powodem.' }] }
        : {})
    },
    patch: () => Promise.resolve(CONTAINERS[0]),
    del: () => Promise.resolve(null),
  },
  downloadFile: () => Promise.resolve(),
  ApiError: class extends Error {},
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => USER }))

globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

import QueuePage from './pages/QueuePage'
import { ToastProvider } from './feedback'

const mount = () => render(
  <ToastProvider><MemoryRouter initialEntries={['/kolejka?spolka=acme']}><QueuePage /></MemoryRouter></ToastProvider>)
const ready = () => waitFor(() => expect(screen.getByText('CSNU0110266')).toBeTruthy())
const selectAll = () => fireEvent.click(document.querySelector('thead .kq-sel input')!)

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); posts.length = 0; USER.role = 'admin' })
afterEach(cleanup)
// kilka pełnych renderów kolejki na test — przy obciążonym runnerze domyślne 5 s bywa za mało

describe('pasek akcji masowych', () => {
  it('pojawia się zamiast paska filtrów po zaznaczeniu, z odmianą licznika; ✕ Odznacz przywraca filtry', async () => {
    mount()
    await ready()
    expect(document.querySelector('.kq-bulk')).toBeNull()
    expect(document.querySelector('.kq-filters')).toBeTruthy()
    fireEvent.click(screen.getByText('CSNU0110266').closest('tr')!.querySelector('.kq-sel input')!)
    await waitFor(() => expect(document.querySelector('.kq-bulk')!.textContent).toContain('1 zaznaczony'))
    expect(document.querySelector('.kq-filters')).toBeNull()
    selectAll()
    await waitFor(() => expect(document.querySelector('.kq-bulk')!.textContent).toContain('2 zaznaczone'))
    fireEvent.click(screen.getByRole('button', { name: /Odznacz/ }))
    await waitFor(() => expect(document.querySelector('.kq-bulk')).toBeNull())
    expect(document.querySelector('.kq-filters')).toBeTruthy()
  })

  it('zmiana statusu = jedno żądanie bulk; potem czyści zaznaczenie i pokazuje wynik z błędem', async () => {
    mount()
    await ready()
    selectAll()
    const sel = await screen.findByRole('combobox', { name: 'Zmień status' })
    fireEvent.change(sel, { target: { value: 'W_PORCIE' } })
    await waitFor(() => expect(posts.some(p => p.path === '/api/containers/bulk/status')).toBe(true))
    expect(posts.filter(p => p.path.startsWith('/api/containers/')).map(p => p.path))
      .toEqual(['/api/containers/bulk/status'])
    expect(posts[0].body).toEqual({ ids: [1, 2], status: 'W_PORCIE' })
    await waitFor(() => expect(document.querySelector('.kq-bulk')).toBeNull())
    expect(await screen.findByText(/1\/2 — Cofnięcie statusu/)).toBeTruthy()
  })

  it('admin widzi Usuń; logistyka nie', async () => {
    mount()
    await ready()
    selectAll()
    expect(await screen.findByRole('button', { name: 'Usuń' })).toBeTruthy()
    cleanup()
    USER.role = 'logistics'
    mount()
    await ready()
    selectAll()
    await screen.findByRole('toolbar', { name: 'Akcje na zaznaczonych' })
    expect(screen.queryByRole('button', { name: 'Usuń' })).toBeNull()
    expect(screen.getByRole('button', { name: /Zleć wycenę/ })).toBeTruthy()
  })

  it('magazyn: brak checkboxów i paska akcji masowych', async () => {
    USER.role = 'warehouse'
    mount()
    await ready()
    expect(document.querySelector('.kq-sel input')).toBeNull()
    expect(document.querySelector('.kq-bulk')).toBeNull()
  })
})
