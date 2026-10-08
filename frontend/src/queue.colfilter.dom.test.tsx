// @vitest-environment jsdom
// Filtry w nagłówkach kolumn „jak w Excelu": lejek → lista unikalnych wartości z licznikami,
// odznaczenie filtruje wiersze, kaskada między kolumnami, „(Puste)", chip w pasku, Escape,
// klik w etykietę nadal sortuje.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const USER = { id: 1, login: 'admin', role: 'admin', full_name: 'Admin',
  must_change_password: false, view_all_companies: true }

const base = {
  company_id: 1, company_name: 'Acme', supplier_name: 'Dostawca A', eta: '2026-08-01', atd: null,
  transport_type: 'kola', status: 'W_TRANSPORCIE', customs_status: 'BRAK', document_status: 'BRAK',
  purchasing_status: 'BRAK', delivery_note: '', incoming_delivery_no: '', purchase_note: '',
  forwarder_name: 'SPEDALFA', document_flow: '', sent_required: null, sent_status: '', is_delayed: false,
  transport_id: null, order_number: null, notify_date: '2026-08-10', warehouse_name: 'ACME',
  sent_number: '', order_numbers: '',
}
const CONTAINERS = [
  { ...base, id: 1, container_no: 'AAAU0000001', vessel: 'MV DEMO DELTA', supplier_name: 'Alfa' },
  { ...base, id: 2, container_no: 'BBBU0000002', vessel: 'MV DEMO DELTA', supplier_name: 'Beta' },
  { ...base, id: 3, container_no: 'CCCU0000003', vessel: 'COSCO', supplier_name: 'Alfa' },
  { ...base, id: 4, container_no: 'DDDU0000004', vessel: '', supplier_name: 'Gamma' },
]

vi.mock('./api', () => ({
  api: {
    put: () => Promise.resolve({}),
    get: (path: string) => Promise.resolve(
      path.startsWith('/api/containers?') ? CONTAINERS
        : path.startsWith('/api/containers/counts') ? {}
          : path.startsWith('/api/ui-config') ? { warehouse_eta_buffer_days: 3 }
            : []),
    post: () => Promise.resolve(CONTAINERS[0]),
    patch: () => Promise.resolve(CONTAINERS[0]),
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

const mount = (initial = '/kolejka?spolka=acme&okres=all') => render(
  <MemoryRouter initialEntries={[initial]}><QueuePage /></MemoryRouter>)
const ready = () => waitFor(() => expect(screen.getByText('AAAU0000001')).toBeTruthy())
const rowNos = () => [...document.querySelectorAll('.kq-no b')].map(b => b.textContent)
const openFilter = (label: string) => {
  fireEvent.click(screen.getByRole('button', { name: `Filtruj: ${label}` }))
  return screen.getByRole('dialog', { name: `Filtruj: ${label}` })
}

beforeEach(() => localStorage.clear())
afterEach(cleanup)

describe('kolejka — filtry w nagłówkach kolumn (Excel)', () => {
  it('lejek otwiera listę unikalnych wartości z licznikami, posortowaną, z „(Puste)" na końcu', async () => {
    mount()
    await ready()
    const dlg = openFilter('Statek')
    const labels = [...dlg.querySelectorAll('.kq-hf-list label')].map(l => l.textContent)
    expect(labels).toEqual(['(Zaznacz wszystko)', 'COSCO1', 'MV DEMO DELTA2', '(Puste)1'])
    expect(document.activeElement).toBe(within(dlg).getByRole('searchbox'))
  })

  it('odznaczenie wartości + OK filtruje wiersze; chip w pasku, × zdejmuje filtr', async () => {
    mount()
    await ready()
    const dlg = openFilter('Statek')
    fireEvent.click(within(dlg).getByText('MV DEMO DELTA'))
    fireEvent.click(within(dlg).getByRole('button', { name: 'OK' }))
    await waitFor(() => expect(rowNos()).toEqual(['CCCU0000003', 'DDDU0000004']))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByRole('button', { name: 'Filtruj: Statek' }).className).toContain('on')
    const bar = document.querySelector('.kq-filters')!
    expect(bar.textContent).toContain('oprócz MV DEMO DELTA')
    fireEvent.click(within(bar.querySelector('.kq-chip') as HTMLElement).getByRole('button'))
    await waitFor(() => expect(rowNos()).toHaveLength(4))
  })

  it('kaskada: lista Dostawcy uwzględnia filtr ze Statku; „(Puste)" działa jako wartość', async () => {
    mount()
    await ready()
    let dlg = openFilter('Statek')
    fireEvent.click(within(dlg).getByText('(Zaznacz wszystko)'))   // odznacz wszystko
    fireEvent.click(within(dlg).getByText('(Puste)'))
    fireEvent.click(within(dlg).getByRole('button', { name: 'OK' }))
    await waitFor(() => expect(rowNos()).toEqual(['DDDU0000004']))
    dlg = openFilter('Dostawca')
    const labels = [...dlg.querySelectorAll('.kq-hf-list label')].map(l => l.textContent)
    expect(labels).toEqual(['(Zaznacz wszystko)', 'Gamma1'])
  })

  it('wyszukiwanie + Enter zawęża do pasujących (jak w Excelu); „Wyczyść wszystkie" zdejmuje', async () => {
    mount()
    await ready()
    const dlg = openFilter('Dostawca')
    fireEvent.change(within(dlg).getByRole('searchbox'), { target: { value: 'alf' } })
    fireEvent.keyDown(within(dlg).getByRole('searchbox'), { key: 'Enter' })
    await waitFor(() => expect(rowNos()).toEqual(['AAAU0000001', 'CCCU0000003']))
    fireEvent.click(screen.getByRole('button', { name: 'Wyczyść wszystkie' }))
    await waitFor(() => expect(rowNos()).toHaveLength(4))
  })

  it('Escape zamyka panel bez zmian i oddaje fokus lejkowi', async () => {
    mount()
    await ready()
    const dlg = openFilter('Statek')
    fireEvent.click(within(dlg).getByText('COSCO'))
    fireEvent.keyDown(within(dlg).getByRole('searchbox'), { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(rowNos()).toHaveLength(4)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Filtruj: Statek' }))
  })

  it('klik w etykietę nagłówka nadal sortuje, klik w lejek nie', async () => {
    mount()
    await ready()
    const th = screen.getByRole('button', { name: 'Filtruj: Dostawca' }).closest('th')!
    fireEvent.click(screen.getByRole('button', { name: 'Filtruj: Dostawca' }))
    expect(th.getAttribute('aria-sort')).toBeNull()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    fireEvent.click(th)
    await waitFor(() => expect(th.getAttribute('aria-sort')).toBe('ascending'))
  })

  it('zły kształt ?kolumny= w URL jest ignorowany (bez wyjątku)', async () => {
    mount('/kolejka?spolka=acme&okres=all&kolumny=%7Bzepsute')
    await ready()
    expect(rowNos()).toHaveLength(4)
  })
})
