// @vitest-environment jsdom
// Kolejka Enterprise (plaster 2): szuflada kontenera — otwarcie klikiem w wiersz,
// ‹ › po kolejności wierszy, ✕ / Esc zamyka, zakładka Historia z audytu.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const USER = { id: 1, login: 'admin', role: 'admin', full_name: 'Admin',
  must_change_password: false, view_all_companies: true }

const base = {
  company_id: 1, company_name: 'Acme', supplier_name: 'Dostawca A', vessel: 'MV DEMO ATLAS',
  eta: '2026-08-01', atd: null, notify_date: '2026-08-10', transport_type: 'kola',
  status: 'W_TRANSPORCIE', customs_status: 'BRAK', document_status: 'BRAK',
  purchasing_status: 'BRAK', order_numbers: '4500001', delivery_note: '',
  incoming_delivery_no: '', purchase_note: '', forwarder_name: 'SPEDALFA', document_flow: '',
  sent_required: null, sent_number: '', sent_status: '', is_delayed: false,
  transport_id: null, order_number: null, warehouse_name: 'DLT', container_size: '40HC',
  port_name: 'Gdańsk', updated_at: '2026-08-01T10:00:00',
}
const CONTAINERS = [
  { ...base, id: 1, container_no: 'MSDU0806613' },
  { ...base, id: 2, container_no: 'TCLU1234568' },
  { ...base, id: 3, container_no: 'HLXU7654324', notify_date: '2026-08-11' },
]
const HISTORY = [
  { id: 11, field: 'status', old_value: 'W_PORCIE', new_value: 'W_TRANSPORCIE', note: 'import',
    user_login: 'jan', created_at: '2026-08-02T08:15:00' },
  { id: 10, field: 'eta', old_value: null, new_value: '2026-08-01', note: '',
    user_login: null, created_at: '2026-08-01T07:00:00' },
]
const historyCalls: string[] = []

vi.mock('./api', () => ({
  api: {
    get: (path: string) => {
      if (path.includes('/history')) { historyCalls.push(path); return Promise.resolve(HISTORY) }
      return Promise.resolve(
        path.startsWith('/api/containers?') ? CONTAINERS
          : path.startsWith('/api/containers/counts') ? {} : [])
    },
    post: () => Promise.resolve({}),
    put: () => Promise.resolve({}),
    patch: () => Promise.resolve({}),
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

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); historyCalls.length = 0 })
afterEach(cleanup)
// kilka pełnych renderów kolejki na test — przy obciążonym runnerze domyślne 5 s bywa za mało

const mount = (url = '/kolejka?spolka=acme') => render(
  <MemoryRouter initialEntries={[url]}><QueuePage /></MemoryRouter>)
const drawerNo = () => document.querySelector('.kq-drawer .kq-dr-no')?.textContent

describe('szuflada kontenera', () => {
  it('klik w wiersz otwiera szufladę; ‹ › idą po kolejności wierszy; ✕ zamyka', async () => {
    mount()
    await waitFor(() => expect(screen.getByText('TCLU1234568')).toBeTruthy())
    fireEvent.click(screen.getByText('TCLU1234568'))
    await waitFor(() => expect(drawerNo()).toBe('TCLU1234568'))
    expect(document.querySelector('.kq-row.active .kq-no b')!.textContent).toBe('TCLU1234568')
    expect(screen.getByText('Port docelowy')).toBeTruthy()
    // Dostawa → Transport: wspólny znacznik z ikoną + spedytor
    const tr = document.querySelector('.kq-drawer .tr-badge--kola')!
    expect(tr.getAttribute('aria-label')).toBe('koła')
    expect(tr.querySelector('svg')).not.toBeNull()
    expect(tr.parentElement!.textContent).toContain('koła · SPEDALFA')
    fireEvent.click(screen.getByRole('button', { name: 'Następny kontener' }))
    await waitFor(() => expect(drawerNo()).toBe('HLXU7654324'))
    // ostatni wiersz — dalej się nie da
    expect((screen.getByRole('button', { name: 'Następny kontener' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Poprzedni kontener' }))
    fireEvent.click(screen.getByRole('button', { name: 'Poprzedni kontener' }))
    await waitFor(() => expect(drawerNo()).toBe('MSDU0806613'))
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij' }))
    await waitFor(() => expect(document.querySelector('.kq-drawer')).toBeNull())
  })

  it('otwarty kontener w URL (?kontener=) i Esc zamyka', async () => {
    mount('/kolejka?spolka=acme&kontener=3')
    await waitFor(() => expect(drawerNo()).toBe('HLXU7654324'))
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(document.querySelector('.kq-drawer')).toBeNull())
  })

  it('zakładka Historia pokazuje wpisy audytu (kto, pole, stara → nowa, czas · źródło)', async () => {
    mount('/kolejka?spolka=acme&kontener=1')
    await waitFor(() => expect(drawerNo()).toBe('MSDU0806613'))
    const tab = await screen.findByRole('tab', { name: /Historia/ })
    await waitFor(() => expect(tab.textContent).toContain('2'))
    fireEvent.click(tab)
    const items = document.querySelectorAll('.kq-dr-hist li')
    expect(items.length).toBe(2)
    expect(items[0].textContent).toContain('jan')
    expect(items[0].textContent).toMatch(/02\.08\.2026 \d{2}:15 · import/)   // UX-041: dd.mm.rrrr, godzina lokalna (strefa runnera)
    expect(items[0].querySelector('i.new')).toBeTruthy()
    expect(items[1].textContent).toContain('system')
    expect(historyCalls[0]).toBe('/api/containers/1/history')
  })
})
