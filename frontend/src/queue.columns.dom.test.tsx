// @vitest-environment jsdom
// Kolejka Enterprise (plaster 4): wybór kolumn (nagłówek + wiersze, zapamiętanie po remount,
// Nr kontenera zablokowany, Przywróć domyślne) i gęstość wiersza.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const USER = { id: 1, login: 'admin', role: 'admin', full_name: 'Admin',
  must_change_password: false, view_all_companies: true }

const CONTAINERS = [{
  id: 1, container_no: 'MSDU0806613', company_id: 1, company_name: 'Acme', supplier_name: 'Dostawca A',
  vessel: 'MV DEMO ATLAS', eta: '2026-08-01', etd: '2026-07-01', atd: null, notify_date: '2026-08-10',
  transport_type: 'kolej', status: 'W_TRANSPORCIE', customs_status: 'BRAK', document_status: 'BRAK',
  purchasing_status: 'BRAK', order_numbers: '4500001', delivery_note: '', incoming_delivery_no: '',
  purchase_note: '', forwarder_name: 'SPEDALFA', document_flow: '', sent_required: null, sent_number: '',
  sent_status: '', is_delayed: false, transport_id: null, order_number: null, warehouse_name: 'DLT',
}]

vi.mock('./api', () => ({
  api: {
    put: () => Promise.resolve({}),  // setPref → zapis profilu widoku (prefs.ts)
    get: (path: string) => Promise.resolve(
      path.startsWith('/api/containers?') ? CONTAINERS
        : path.startsWith('/api/containers/counts') ? {} : []),
    post: () => Promise.resolve({}),
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

beforeEach(() => { localStorage.clear(); sessionStorage.clear() })
afterEach(cleanup)

const mount = () => render(
  <MemoryRouter initialEntries={['/kolejka?spolka=acme']}><QueuePage /></MemoryRouter>)
const ready = () => waitFor(() => expect(screen.getByText('MSDU0806613')).toBeTruthy())
const headers = () => [...document.querySelectorAll('.kq-table thead th')].map(th => th.textContent)
// wybór kolumn i gęstość siedzą w menu „Widok"
const openColumns = () => fireEvent.click(screen.getByRole('button', { name: 'Widok' }))
const check = (label: string) => fireEvent.click(screen.getByRole('checkbox', { name: label }))

describe('wybór kolumn i gęstość', () => {
  it('ukrycie kolumny zmienia nagłówek i wiersze; dodatkowe pole się pojawia; zapamiętane po remount', async () => {
    const first = mount()
    await ready()
    expect(headers()).toContain('Statek')
    expect(headers()).not.toContain('Transport')
    expect(document.querySelector('.kq-row .kq-c-vessel')!.textContent).toBe('MV DEMO ATLAS')
    openColumns()
    check('Statek')
    check('Transport')
    await waitFor(() => expect(headers()).not.toContain('Statek'))
    expect(headers()).toContain('Transport')
    expect(document.querySelector('.kq-row .kq-c-vessel')).toBeNull()
    expect(document.querySelector('.kq-row .kq-c-transport')!.textContent).toBe('kolej')
    // znacznik z ikoną w kolorze trybu (wariant C, styl 1 — kontener na wagonie)
    expect(document.querySelector('.kq-row .kq-c-transport .tr-badge--kolej svg')).not.toBeNull()
    // Nr kontenera zablokowany
    expect((screen.getByRole('checkbox', { name: 'Nr kontenera' }) as HTMLInputElement).disabled).toBe(true)
    first.unmount()
    mount()
    await ready()
    expect(headers()).not.toContain('Statek')
    expect(headers()).toContain('Transport')
    openColumns()
    fireEvent.click(screen.getByRole('button', { name: 'Przywróć domyślne' }))
    await waitFor(() => expect(headers()).toContain('Statek'))
    expect(headers()).not.toContain('Transport')
  })

  it('domyślnie Kompaktowy (bez zapisu); przełącznik w menu Widok, wybór Komfortowy zapamiętany', async () => {
    const first = mount()
    await ready()
    expect(document.querySelector('.kq-table')!.className).toContain('dense')
    expect(localStorage.getItem('kqDense')).toBeNull()   // domyślny nie jest zapisywany
    openColumns()
    fireEvent.click(screen.getByRole('radio', { name: 'Komfortowy' }))
    await waitFor(() => expect(document.querySelector('.kq-table')!.className).not.toContain('dense'))
    first.unmount()
    mount()
    await ready()
    expect(document.querySelector('.kq-table')!.className).not.toContain('dense')
  })

  it('zapisany wcześniej wybór „zwykła" (kqDense=0 z plastra 4) nie jest nadpisywany domyślnym', async () => {
    localStorage.setItem('kqDense', '0')
    mount()
    await ready()
    expect(document.querySelector('.kq-table')!.className).not.toContain('dense')
    expect(localStorage.getItem('kqDense')).toBe('0')
  })

  it('kolumna pusta w całej widocznej tabeli jest ukryta, stopka mówi które (UX-022)', async () => {
    mount()
    await ready()
    // Wypełn. (brak danych), Demurrage (brak terminu), Odprawa (BRAK) — puste; Statek nie
    await waitFor(() => expect(headers()).not.toContain('Wypełn.'))
    expect(headers()).not.toContain('Demurrage')
    expect(headers()).not.toContain('Odprawa')
    expect(headers()).toContain('Statek')
    // żadnego nagłówka „—" (4 takie kolumny w kolejce nic nie mówiły)
    expect(headers().some(h => h?.includes('—'))).toBe(false)
    // stopka liczy się z tych samych danych, ale może dojść render później (flaky w CI)
    await waitFor(() => expect(document.querySelector('.kq-foot')!.textContent)
      .toContain('Puste kolumny ukryte: Odprawa, Demurrage, Wypełn.'))
  })

  it('kody kolorów: pasek etapu z podpowiedzią, legenda w stopce (UX-012)', async () => {
    mount()
    await ready()
    const sel = document.querySelector('.kq-row td.kq-sel') as HTMLElement
    expect(sel.title).toBe('Etap: Transport morski')
    const legend = screen.getByRole('button', { name: 'Legenda kolorów' })
    expect(legend.closest('.kq-foot')).not.toBeNull()
    fireEvent.click(legend)
    const tip = (screen.getByRole('tooltip').textContent ?? '').toLowerCase()
    for (const part of ['kropka', 'pasek', 'tło']) expect(tip).toContain(part)
  })
})
