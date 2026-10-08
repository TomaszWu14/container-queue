// @vitest-environment jsdom
// Strażnik audytu frontendu: wyścigi odpowiedzi (wolna starsza odpowiedź nie nadpisuje
// nowszej), useFillSummary po anulowaniu, mailto zaproszenia bez hasła, klawiatura.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { mdAt } from './mdRoute.testutil'

vi.mock('../i18n', async () => {
  const { createContext } = await import('react')
  return {
    useT: () => (key: string) => key,
    LangContext: createContext({ lang: 'pl', setLang: () => {} }),
    localeFor: () => 'pl-PL',
  }
})
vi.mock('../App', () => ({ useUser: () => ({ id: 1, login: 'a', role: 'admin' }) }))

interface Deferred { resolve: (v: unknown) => void; reject: (e: unknown) => void }
// ścieżki z `held` wiszą, dopóki test ich ręcznie nie rozwiąże (w kolejności wywołań)
let held: string[] = []
let pending: Deferred[] = []
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
apiGet.mockImplementation((path: string) => {
  if (held.some(p => path.startsWith(p)))
    return new Promise((resolve, reject) => { pending.push({ resolve, reject }) })
  return Promise.resolve(path.includes('/count') ? { count: 0 } : path.includes('/ml/') ? null : [])
})
vi.mock('../api', () => ({
  api: { get: apiGet, post: vi.fn(), patch: vi.fn(), put: vi.fn(), del: vi.fn() },
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

import NamedTab from './admin/NamedTab'
import OrderLinesPanel from './OrderLinesPanel'
import MaterialsTab from './admin/MaterialsTab'
import SupplierMapsTab from './masterdata/SupplierMapsTab'
import MasterDataPage from './MasterDataPage'
import { useFillSummary } from './queueFill'
import { inviteMailUrl } from './admin/shared'
import KnowledgePanel from '../KnowledgePanel'
import type { Container, KnowledgeScope } from '../types'

afterEach(() => { cleanup(); held = []; pending = []; apiGet.mockClear() })

// rozwiąż kolejno: najpierw NOWSZE (index 1), potem starsze (index 0)
async function resolveOutOfOrder(newer: unknown, older: unknown, newText: string) {
  await act(async () => { pending[1].resolve(newer) })
  await screen.findByText(newText)
  await act(async () => { pending[0].resolve(older) })
}

describe('wyścigi odpowiedzi — starsza odpowiedź nie nadpisuje nowszej', () => {
  it('NamedTab: zmiana endpointu', async () => {
    held = ['/api/ports', '/api/suppliers']
    const { rerender } = render(<NamedTab endpoint="/api/ports" />)
    rerender(<NamedTab endpoint="/api/suppliers" />)
    await waitFor(() => expect(pending).toHaveLength(2))
    await resolveOutOfOrder([{ id: 2, name: 'NOWY' }], [{ id: 1, name: 'STARY' }], 'NOWY')
    expect(screen.queryByText('STARY')).toBeNull()
  })

  it('OrderLinesPanel: zmiana kontenera', async () => {
    held = ['/api/containers/']
    const line = (material: string) => [{ order_number: 'PO1', position: '10', material,
      description: '', ordered_qty: '1', received_qty: '', invoiced_qty: '',
      receipt_id: null, status: 'none', status_invoice: 'none' }]
    const { rerender } = render(
      <OrderLinesPanel container={{ id: 1 } as Container} />)
    rerender(<OrderLinesPanel container={{ id: 2 } as Container} />)
    await waitFor(() => expect(pending).toHaveLength(2))
    await resolveOutOfOrder(line('M-NEW'), line('M-OLD'), 'M-NEW')
    expect(screen.queryByText('M-OLD')).toBeNull()
  })

  it('OrderLinesPanel: błąd ładowania jest pokazany, nie połknięty', async () => {
    held = ['/api/containers/']
    render(<OrderLinesPanel container={{ id: 1 } as Container} />)
    await waitFor(() => expect(pending).toHaveLength(1))
    await act(async () => { pending[0].reject(new Error('Błąd 500')) })
    expect(await screen.findByText('Błąd 500')).toBeTruthy()
  })

  it('MaterialsTab: kolejne wyszukiwanie', async () => {
    held = ['/api/materials?']
    render(<MaterialsTab />)
    await waitFor(() => expect(pending).toHaveLength(1))
    fireEvent.change(screen.getByPlaceholderText('materialsSearch'), { target: { value: 'x' } })
    fireEvent.submit(screen.getByPlaceholderText('materialsSearch').closest('form')!)
    await waitFor(() => expect(pending).toHaveLength(2))
    const m = (ref_code: string, id: number) => [{ id, ref_code, is_active: true, name_pl: '', overrides: [] }]
    await resolveOutOfOrder(m('REF-NEW', 2), m('REF-OLD', 1), 'REF-NEW')
    expect(screen.queryByText('REF-OLD')).toBeNull()
  })

  it('SupplierMapsTab: kolejne wyszukiwanie', async () => {
    held = ['/api/supplier-material-maps']
    render(<SupplierMapsTab companies={[]} />)
    await waitFor(() => expect(pending).toHaveLength(1))
    const input = screen.getByPlaceholderText('mdSearch')
    fireEvent.change(input, { target: { value: 'x' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(pending).toHaveLength(2))
    const r = (code: string, id: number) => [{ id, company_id: 1, supplier_id: 1,
      supplier_code: code, ref_code: '', note: '' }]
    await resolveOutOfOrder(r('SC-NEW', 2), r('SC-OLD', 1), 'SC-NEW')
    expect(screen.queryByText('SC-OLD')).toBeNull()
  })

  it('KnowledgePanel: zmiana ekranu (scopes)', async () => {
    held = ['/api/knowledge/notes']
    const scope = (k: string) => [{ scope_type: 'screen', scope_key: k }] as KnowledgeScope[]
    const { rerender } = render(<KnowledgePanel scopes={scope('a')} />)
    rerender(<KnowledgePanel scopes={scope('b')} />)
    await waitFor(() => expect(pending).toHaveLength(2))
    const note = (id: number, title: string) => [{ id, title, body: '', url: '',
      scope_type: 'screen', scope_key: 'x', is_active: true, created_at: '', created_by_name: '' }]
    await act(async () => { pending[1].resolve(note(2, 'KB-NEW')) })
    fireEvent.click(screen.getByLabelText('kbPanelTitle'))
    await screen.findByText('KB-NEW')
    await act(async () => { pending[0].resolve(note(1, 'KB-OLD')) })
    expect(screen.queryByText('KB-OLD')).toBeNull()
  })

  it('Master data › Magazyny: błąd ładowania słownika widoczny', async () => {
    held = ['/api/warehouses']
    render(mdAt('magazyny', <MasterDataPage />))
    await waitFor(() => expect(pending).toHaveLength(1))
    await act(async () => { pending[0].reject(new Error('Błąd 503')) })
    expect(await screen.findByText('Błąd 503')).toBeTruthy()
  })
})

describe('useFillSummary — anulowanie w trakcie pętli', () => {
  it('id z nieukończonej paczki są pobierane ponownie po wznowieniu', async () => {
    held = ['/api/containers/fill-summary']
    const { rerender } = renderHook(({ on }) => useFillSummary([1, 2], on),
      { initialProps: { on: true } })
    await waitFor(() => expect(pending).toHaveLength(1))
    rerender({ on: false })          // anulowanie zanim paczka wróciła
    rerender({ on: true })
    await waitFor(() => expect(pending).toHaveLength(2))   // ponowne żądanie, nie zgubione
    expect(apiGet.mock.calls.filter(c => String(c[0]).includes('ids=1,2'))).toHaveLength(2)
  })
})

describe('zaproszenie mailto', () => {
  it('nie zawiera hasła, adres i treść są kodowane', () => {
    const url = inviteMailUrl({ login: 'jan', full_name: 'Jan & Syn', email: 'a+b@x.pl?cc=evil@y.pl' })
    expect(url.startsWith('mailto:a%2Bb%40x.pl%3Fcc%3Devil%40y.pl?subject=')).toBe(true)
    expect(decodeURIComponent(url)).not.toMatch(/Hasło tymczasowe:/)
    expect(url).not.toContain('&cc=')
    expect(url).toContain(encodeURIComponent('Jan & Syn'))
  })
})
