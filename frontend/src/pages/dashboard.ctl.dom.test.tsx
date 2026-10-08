// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DashboardPage from './DashboardPage'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))
vi.mock('react-router-dom', async (importOriginal) => ({
  ...await importOriginal<typeof import('react-router-dom')>(),
  useNavigate: () => navigateMock,
}))

// Wieża kontrolna (dashboard 1a): kafelki + lista działań z priorytetem + filtr spółki.
vi.mock('../i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../i18n')>()
  const pl = actual.DICTS.pl as Record<string, string>
  return {
    ...actual,
    // passthrough — asertujemy na danych, nie etykietach — poza summary_key (sigSum_*),
    // bo test sprawdza wyrenderowany szczegół ('+8 dni'), który idzie przez prawdziwy słownik PL
    useT: () => (key: string) => (key.startsWith('sigSum_') ? pl[key] ?? key : key),
  }
})
vi.mock('../DocumentsW5', () => ({ DocsGapsCard: () => null }))

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({ api: { get: apiGet }, errorMessage: (e: unknown) => String(e) }))

interface Signal {
  container_id: number; container_no: string; company_name: string | null
  supplier_name: string | null; port_name: string | null
  eta: string | null; notify_date: string | null; status: string
  type: 'delayed'|'demurrage'|'stuck'|'missing_avizo'|'missing_eta'|'missing_docs'
  score: number; urgency_days: number; cost_eur: number | null
  action_kind: 'container'|'avizo-form'|'documents'
  summary_key: string; summary_params: Record<string, string | number>
}

const DASH: {
  today: number; tomorrow: number; in_transit: number; at_port: number
  customs_in_progress: number; delayed: number
  today_list: unknown[]; demurrage_list: unknown[]; delayed_list: unknown[]
  action_feed: Signal[]
} = {
  today: 11, tomorrow: 14, in_transit: 6, at_port: 334, customs_in_progress: 3, delayed: 3,
  today_list: [], demurrage_list: [{ id: 9 }, { id: 8 }],
  delayed_list: [
    { id: 1, container_no: 'AAA1', company_name: 'Acme', supplier_name: 'FICTIVA',
      port_name: 'Ningbo', eta: '2026-09-14', notify_date: '2026-09-18', delay_days: 8, status: 'W_PORCIE' },
    { id: 2, container_no: 'BBB2', company_name: 'Acme', supplier_name: 'EMY',
      port_name: 'Shanghai', eta: '2026-09-16', notify_date: null, delay_days: 4, status: 'W_PORCIE' },
    { id: 3, container_no: 'CCC3', company_name: 'Borealis', supplier_name: 'BLUESAIL',
      port_name: 'Qingdao', eta: '2026-09-19', notify_date: '2026-09-20', delay_days: 1, status: 'ODPRAWA' },
  ],
  action_feed: [
    { container_id: 1, container_no: 'AAA1', company_name: 'Acme', supplier_name: 'FICTIVA',
      port_name: 'Ningbo', eta: '2026-09-14', notify_date: '2026-09-18', status: 'W_PORCIE',
      type: 'delayed', score: 80, urgency_days: 8, cost_eur: null, action_kind: 'container',
      summary_key: 'sigSum_delayed', summary_params: { days: 8 } },
    { container_id: 2, container_no: 'BBB2', company_name: 'Acme', supplier_name: 'EMY',
      port_name: 'Shanghai', eta: '2026-09-16', notify_date: null, status: 'W_PORCIE',
      type: 'delayed', score: 40, urgency_days: 4, cost_eur: null, action_kind: 'container',
      summary_key: 'sigSum_delayed', summary_params: { days: 4 } },
    { container_id: 3, container_no: 'CCC3', company_name: 'Borealis', supplier_name: 'BLUESAIL',
      port_name: 'Qingdao', eta: '2026-09-19', notify_date: '2026-09-20', status: 'ODPRAWA',
      type: 'delayed', score: 10, urgency_days: 1, cost_eur: null, action_kind: 'container',
      summary_key: 'sigSum_delayed', summary_params: { days: 1 } },
  ],
}

function mount(overrides: Partial<typeof DASH> = {}) {
  apiGet.mockImplementation((url: string) =>
    url.includes('/api/stats/dashboard') ? Promise.resolve({ ...DASH, ...overrides })
      : Promise.resolve({ created: [], status: [], eta: [] }))
  render(<MemoryRouter><DashboardPage /></MemoryRouter>)
}

afterEach(() => { cleanup(); apiGet.mockReset(); navigateMock.mockReset() })

describe('Wieża kontrolna — dashboard 1a', () => {
  it('lista działań: priorytet P1/P2/P3 wg dni opóźnienia, sortowana malejąco', async () => {
    mount()
    await screen.findByText('AAA1')
    // 8 dni → P1, 4 → P2, 1 → P3
    expect(screen.getByText('P1')).toBeTruthy()
    expect(screen.getByText('P2')).toBeTruthy()
    expect(screen.getByText('P3')).toBeTruthy()
    // sortowanie: pierwszy wiersz danych to największe opóźnienie (AAA1)
    const rows = document.querySelectorAll('tbody tr')
    expect(rows[0].querySelector('.mono')?.textContent).toBe('AAA1')
  })

  it('UX-018: jedna akcja „Otwórz kolejkę” (link panelu, nie drugi przycisk w nagłówku)', async () => {
    mount()
    await screen.findByText('AAA1')
    const links = screen.getAllByText(/dashOpenQueue/)
    expect(links).toHaveLength(1)
    expect(links[0].closest('a')!.className).toContain('link-like')
  })

  it('filtr spółki zawęża listę działań', async () => {
    mount()
    await screen.findByText('CCC3')
    const select = screen.getByLabelText('company') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'Borealis' } })
    await waitFor(() => {
      expect(screen.queryByText('AAA1')).toBeNull()      // Acme zniknął
      expect(screen.getByText('CCC3')).toBeTruthy()       // Borealis został
    })
  })

  it('deep-link: action_kind documents/avizo-form dokłada ?akcja=, container nie', async () => {
    mount({
      action_feed: [
        { container_id: 5, container_no: 'DOC5', company_name: 'Acme', supplier_name: null,
          port_name: null, eta: null, notify_date: null, status: 'W_PORCIE', type: 'missing_docs',
          score: 5, urgency_days: 0, cost_eur: null, action_kind: 'documents',
          summary_key: 'sigSum_missing_docs', summary_params: {} },
        { container_id: 6, container_no: 'AVI6', company_name: 'Acme', supplier_name: null,
          port_name: null, eta: null, notify_date: null, status: 'W_PORCIE', type: 'missing_avizo',
          score: 4, urgency_days: 0, cost_eur: null, action_kind: 'avizo-form',
          summary_key: 'sigSum_missing_avizo', summary_params: {} },
        { container_id: 7, container_no: 'CNT7', company_name: 'Acme', supplier_name: null,
          port_name: null, eta: null, notify_date: null, status: 'W_PORCIE', type: 'delayed',
          score: 3, urgency_days: 1, cost_eur: null, action_kind: 'container',
          summary_key: 'sigSum_delayed', summary_params: { days: 1 } },
      ],
    })
    fireEvent.click(await screen.findByText('DOC5'))
    expect(navigateMock).toHaveBeenLastCalledWith('/kontenery/5?akcja=documents')
    fireEvent.click(screen.getByText('AVI6'))
    expect(navigateMock).toHaveBeenLastCalledWith('/kontenery/6?akcja=avizo-form')
    fireEvent.click(screen.getByText('CNT7'))
    expect(navigateMock).toHaveBeenLastCalledWith('/kontenery/7')
  })

  it('renderuje jedną listę Co dziś z action_feed (summary + typ)', async () => {
    mount({
      action_feed: [{
        container_id: 7, container_no: 'MEDU1234562', company_name: 'ACME',
        supplier_name: null, port_name: 'Gdańsk', eta: null, notify_date: null,
        status: 'W_PORCIE', type: 'missing_eta', score: 3, urgency_days: 0,
        cost_eur: null, action_kind: 'container',
        summary_key: 'sigSum_missing_eta', summary_params: {},
      }],
    })
    // bez dubla „Brak ETA: brak ETA” — typ wystarcza, pusty szczegół nie jest doklejany
    const row = (await screen.findByText('MEDU1234562')).closest('tr')!
    expect(row.querySelectorAll('td')[2].textContent).toBe('sig_missing_eta')
  })

  it('szczegół sygnału bez powtarzania typu: „Opóźniony: +8 dni”', async () => {
    mount()
    const row = (await screen.findByText('AAA1')).closest('tr')!
    expect(row.querySelectorAll('td')[2].textContent).toBe('sig_delayed: +8 dni')
  })

  it('A3: demurrage — w „CO” sam typ ryzyka, kwota tylko w „KOSZT”', async () => {
    mount({
      action_feed: [{
        container_id: 8, container_no: 'DEMU0000001', company_name: 'ACME',
        supplier_name: null, port_name: 'Gdańsk', eta: null, notify_date: null,
        status: 'W_PORCIE', type: 'demurrage', score: 50, urgency_days: 2,
        cost_eur: 1234, action_kind: 'container',
        summary_key: 'sigSum_demurrage', summary_params: { cost: 1234 },
      }],
    })
    const row = (await screen.findByText('DEMU0000001')).closest('tr')!
    const cells = row.querySelectorAll('td')
    expect(cells[2].textContent).toBe('sig_demurrage')
    expect(row.textContent!.match(/1234/g)).toHaveLength(1)   // tylko „KOSZT”
  })

  it('C6: błąd ładowania zostawia nagłówek strony nad komunikatem', async () => {
    apiGet.mockImplementation(() => Promise.reject(new Error('Serwer nie odpowiedział')))
    render(<MemoryRouter><DashboardPage /></MemoryRouter>)
    expect(await screen.findByText(/Serwer nie odpowiedział/)).toBeTruthy()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('ctlTitle')
  })
})
