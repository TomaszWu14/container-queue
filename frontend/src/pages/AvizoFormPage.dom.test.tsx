// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AvizoFormPage from './AvizoFormPage'

// klucz i18n + język (useT(lang)) — widać, że strona bierze język z odpowiedzi API
vi.mock('../i18n', () => ({
  useT: (lang?: string) => (key: string) => (lang ? `${lang}:${key}` : key),
}))

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/avizo/tok123']}>
      <Routes><Route path="/avizo/:token" element={<AvizoFormPage />} /></Routes>
    </MemoryRouter>,
  )
}

const res = (status: number, body: unknown = {}) =>
  ({ ok: status < 300, status, json: async () => body })

const ITEM = { container_id: 7, container_no: 'MSCU1234571', vessel: 'MV DEMO BOREAS',
  notify_date: '2026-10-05', warehouse: 'DLT', slot_time: '', planning_status: 'PROPOZYCJA',
  slots: [{ time: '07:00', free: 0 }, { time: '09:00', free: 1 }] }
const DATA = { stage: 1, language: 'en', forwarder: 'FW', company: 'ACME', note: '',
  reject_comment: '', items: [ITEM] }

describe('AvizoFormPage — stany ładowania', () => {
  it('5xx pokazuje retry, nie „nie istnieje"', async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(500))
    vi.stubGlobal('fetch', fetchMock)
    renderPage()
    fireEvent.click(await screen.findByText('retry'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(screen.queryByText('avizoNotFound')).toBeNull()
  })

  it.each([404, 410])('%i → formularz nie istnieje/wygasł', async status => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res(status)))
    renderPage()
    expect(await screen.findByText('avizoNotFound')).toBeTruthy()
  })

  it('409 → „formularz już wysłany" bez danych', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      res(409, { detail: { code: 'already_submitted', message: 'Formularz już wysłany.' } })))
    renderPage()
    expect(await screen.findByText(/av1Done$/)).toBeTruthy()
    expect(screen.queryByText('MSCU1234571')).toBeNull()
  })
})

describe('AvizoFormPage — etap 1', () => {
  it('kontener tylko do odczytu, bez pól kierowcy, język z API', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res(200, DATA)))
    renderPage()
    expect(await screen.findByText('MSCU1234571')).toBeTruthy()
    expect(screen.getByText('MV DEMO BOREAS · DLT')).toBeTruthy()
    expect(screen.getByText('en:av1Title')).toBeTruthy()
    expect(screen.queryByText(/driverName/)).toBeNull()
  })

  it('potwierdzenie ze slotem: zajęty slot wyłączony, POST JSON z decyzją → stan wysłany', async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST' ? res(200, { ok: true, total: 1 }) : res(200, DATA))
    vi.stubGlobal('fetch', fetchMock)
    renderPage()
    const select = await screen.findByLabelText('en:avizoSlot') as HTMLSelectElement
    expect([...select.options].find(o => o.value === '07:00')!.disabled).toBe(true)
    fireEvent.change(select, { target: { value: '09:00' } })
    fireEvent.click(screen.getByText('en:av1Submit'))
    expect(await screen.findByText(/av1Done$/)).toBeTruthy()
    const [, init] = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')!
    expect((init!.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect((init!.headers as Record<string, string>)['X-Requested-With']).toBe('XMLHttpRequest')
    expect(JSON.parse(String(init!.body))).toEqual({ items: [{ container_id: 7,
      decision: 'confirmed', proposed_date: null, slot_time: '09:00', comment: '' }] })
  })

  it('zmiana terminu wymaga daty; nowa data odświeża sloty', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return res(200, { ok: true })
      if (url.includes('/slots')) return res(200, [{ time: '11:00', free: 2 }])
      return res(200, DATA)
    })
    vi.stubGlobal('fetch', fetchMock)
    renderPage()
    fireEvent.click(await screen.findByLabelText('en:av1DateChange'))
    fireEvent.click(screen.getByText('en:av1Submit'))
    expect(await screen.findByText('en:av1DateRequired')).toBeTruthy()
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === 'POST')).toBe(false)

    fireEvent.change(screen.getByLabelText('en:av1NewDate'), { target: { value: '2026-10-09' } })
    const select = await screen.findByLabelText('en:avizoSlot') as HTMLSelectElement
    await waitFor(() => expect([...select.options].map(o => o.value)).toContain('11:00'))
    fireEvent.change(select, { target: { value: '11:00' } })
    fireEvent.click(screen.getByText('en:av1Submit'))
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')
      expect(JSON.parse(String(post![1]!.body)).items[0]).toMatchObject(
        { decision: 'date_change', proposed_date: '2026-10-09', slot_time: '11:00' })
    })
  })

  it('problem wymaga komentarza; 409 „slot zajęty" to błąd, nie koniec formularza', async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => init?.method === 'POST'
      ? res(409, { detail: { code: 'slot_taken', message: 'Okno 09:00 dnia 2026-10-05 dla X jest już zajęty.' } })
      : res(200, DATA))
    vi.stubGlobal('fetch', fetchMock)
    renderPage()
    fireEvent.click(await screen.findByLabelText('en:av1Problem'))
    fireEvent.click(screen.getByText('en:av1Submit'))
    expect(await screen.findByText('en:av1ProblemRequired')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('en:av1Comment'), { target: { value: 'port strike' } })
    fireEvent.click(screen.getByText('en:av1Submit'))
    expect(await screen.findByText(/jest już zajęty/)).toBeTruthy()
    expect(screen.getByText('MSCU1234571')).toBeTruthy()
  })

  it('409 already_submitted przy POST → stan wysłany (po kodzie, nie po treści)', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => init?.method === 'POST'
      ? res(409, { detail: { code: 'already_submitted', message: 'Slot-owy tekst bez znaczenia' } })
      : res(200, DATA)))
    renderPage()
    fireEvent.click(await screen.findByText('en:av1Submit'))
    expect(await screen.findByText(/av1Done$/)).toBeTruthy()
  })
})

// awizacja w aplikacji (2026-10-07): spedytor z kontem — ten sam formularz, adresy API po id
describe('AvizoFormPage — w aplikacji (requestId)', () => {
  it('czyta i wysyła przez /api/avizo-forwarder/{id}', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res(200, DATA)).mockResolvedValue(res(200, { ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    render(<MemoryRouter><AvizoFormPage requestId={42} /></MemoryRouter>)
    fireEvent.click(await screen.findByText('en:av1Submit'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/avizo-forwarder/42/confirm',
      expect.objectContaining({ method: 'POST' })))
    expect(fetchMock.mock.calls[0][0]).toBe('/api/avizo-forwarder/42')
  })
})
