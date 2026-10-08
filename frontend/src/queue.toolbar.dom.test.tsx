// @vitest-environment jsdom
// Porządki toolbara kolejki (decyzje 2, 3, 6, 7, 9, 10, 12, 13 z 2026-09-03-kolejka-ui-polish):
// bez licznika „rozwiniętych", edycja jako przełącznik stanu, wspólne menu „Widok"
// (kolumny + gęstość), sekcja per-magazyn ukryta przy <2 magazynach.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const USER: Record<string, unknown> = { id: 1, login: 'admin', role: 'admin', full_name: 'Admin',
  must_change_password: false, view_all_companies: true }

const base = {
  company_id: 1, company_name: 'Acme', supplier_name: 'Dostawca A', vessel: 'MV DEMO ATLAS',
  eta: '2026-08-01', atd: null, transport_type: 'kola', status: 'W_TRANSPORCIE',
  customs_status: 'BRAK', document_status: 'BRAK', purchasing_status: 'BRAK',
  delivery_note: '', incoming_delivery_no: '18001', purchase_note: '',
  forwarder_name: 'SPEDALFA', document_flow: '', sent_required: null, sent_status: '',
  is_delayed: false, transport_id: null, order_number: null,
}

// jeden magazyn w całym zakresie — sekcja „per magazyn" ma zostać ukryta (decyzja 3)
const CONTAINERS_ONE_WH = [
  { ...base, id: 1, container_no: 'CSNU0110266', notify_date: '2026-08-10',
    warehouse_name: 'ACME', sent_number: '180022585', order_numbers: '4500617421' },
  { ...base, id: 2, container_no: 'TIIU9152821', notify_date: '2026-08-11',
    warehouse_name: 'ACME', sent_number: '180023076', order_numbers: '4500618818' },
]

const COMPANIES = [{ id: 1, code: 'ACME', name: 'Acme' }, { id: 4, code: 'COBALT', name: 'Cobalt' }]
const { apiPost } = vi.hoisted(() => ({ apiPost: vi.fn() }))

vi.mock('./api', () => ({
  api: {
    put: () => Promise.resolve({}),  // setPref → zapis profilu widoku (prefs.ts)
    get: (path: string) => Promise.resolve(
      path.startsWith('/api/containers?') ? CONTAINERS_ONE_WH
        : path.startsWith('/api/containers/counts') ? {}
          : path.startsWith('/api/ui-config') ? { warehouse_eta_buffer_days: 3 }
            : path === '/api/companies' ? COMPANIES
              : []),
    post: (...a: unknown[]) => { apiPost(...a); return Promise.resolve(CONTAINERS_ONE_WH[0]) },
    patch: () => Promise.resolve(CONTAINERS_ONE_WH[0]),
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

const mount = (spolka = 'acme', archive = false) => render(
  <MemoryRouter initialEntries={[`/kolejka?spolka=${spolka}`]}><QueuePage archive={archive} /></MemoryRouter>)

const ready = () => waitFor(() => expect(screen.getByText('CSNU0110266')).toBeTruthy())

beforeEach(() => { localStorage.clear(); apiPost.mockClear(); USER.role = 'admin' })
afterEach(cleanup)

describe('kolejka — porządki toolbara', () => {
  it('nie pokazuje licznika „rozwiniętych" (decyzja 9)', async () => {
    mount()
    await ready()
    expect(document.body.textContent).not.toMatch(/rozwiniętych/)
  })

  it('sekcja per-magazyn jest ukryta, gdy w zakresie jest jeden magazyn (decyzja 3)', async () => {
    mount()
    await ready()
    expect(document.querySelector('.qs-warehouses')).toBeNull()
  })

  it('przełącznik edycji (kłódka) pokazuje stan w aria-pressed i tooltipie (decyzja 10)', async () => {
    mount()
    await ready()
    const btn = screen.getByRole('button', { name: 'Edycja' })
    expect(btn.getAttribute('aria-pressed')).toBe('false')
    expect(btn.title).toContain('Edycja wyłączona')
    fireEvent.click(btn)
    await waitFor(() => expect(btn.getAttribute('aria-pressed')).toBe('true'))
    expect(btn.className).toContain('unlocked')
    expect(btn.title).toBe('Edycja włączona — przeciągaj kontenery na dni')
  })

  it('skróty „/" i Ctrl+K poza polami edycji ustawiają fokus w wyszukiwarce kolejki', async () => {
    mount()
    await ready()
    const input = document.querySelector('input.qsearch') as HTMLInputElement
    fireEvent.keyDown(document.body, { key: '/' })
    expect(document.activeElement).toBe(input)
    input.blur()
    fireEvent.keyDown(document.body, { key: 'k', ctrlKey: true })
    expect(document.activeElement).toBe(input)
    // w polu edycji „/" to zwykły znak — skrót nie przechwytuje
    const other = document.createElement('input')
    document.body.appendChild(other)
    other.focus()
    fireEvent.keyDown(other, { key: '/' })
    expect(document.activeElement).toBe(other)
    other.remove()
  })

  it('przycisk „+ Dodaj" otwiera formularz (decyzja D3)', async () => {
    mount()
    await ready()
    fireEvent.click(screen.getByRole('button', { name: /Dodaj/ }))
    await waitFor(() => expect(document.querySelector('.modal')?.textContent).toContain('Dodaj kontener'))
  })

  it('kontener dodany w kolejce modułu trafia do spółki tego modułu (review D3)', async () => {
    mount('cobalt')
    await ready()
    fireEvent.click(screen.getByRole('button', { name: /Dodaj/ }))
    const form = await waitFor(() => document.querySelector('.modal form') as HTMLFormElement)
    await waitFor(() => expect(form.querySelector('option[value="4"]')).toBeTruthy())
    fireEvent.submit(form)
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    expect(apiPost.mock.calls[0][1]).toMatchObject({ company_id: 4 })
  })

  it('menu „⋯" ma destrukcyjne „Wyczyść kolejkę" tylko dla admina (logistyka go nie widzi)', async () => {
    mount()
    await ready()
    expect(screen.queryByText(/Wyczyść kolejkę/)).toBeNull()   // nie w pasku — dopiero w menu
    fireEvent.click(document.querySelector('.kq-more-menu')!)
    const item = screen.getByText(/Wyczyść kolejkę/).closest('button')!
    expect(item.className).toContain('kq-danger')
    expect(item.closest('[role="menu"]')).toBeTruthy()
    cleanup()
    USER.role = 'logistics'
    mount()
    await ready()
    const more = document.querySelector('.kq-more-menu')
    if (more) fireEvent.click(more)
    expect(screen.queryByText(/Wyczyść kolejkę/)).toBeNull()
  })

  it('bez przycisku „Dodaj kontener" dla ról tylko-do-odczytu i w archiwum (review D3)', async () => {
    USER.role = 'warehouse'
    mount()
    await ready()
    expect(screen.queryByRole('button', { name: /Dodaj/ })).toBeNull()
    cleanup()
    USER.role = 'admin'
    mount('acme', true)
    await ready()
    expect(screen.queryByRole('button', { name: /Dodaj/ })).toBeNull()
  })
})
