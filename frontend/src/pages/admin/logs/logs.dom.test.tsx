// @vitest-environment jsdom
import { createContext } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../../../api', () => ({ api: { get: apiGet }, errorMessage: (e: unknown) => String(e) }))
vi.mock('../../../i18n', () => ({ useT: () => (key: string) => key, LangContext: createContext({ lang: 'pl' }) }))
vi.mock('../../../dates', () => ({
  formatDateTime: (s: string) => `D:${s}`,
  relTime: (s: string) => `rel:${s}`,
  parseServerTs: (iso: string) => {
    const hasZone = /[Zz]$|[+-]\d\d:?\d\d$/.test(iso)
    return new Date(hasZone || !iso.includes('T') ? iso : `${iso}Z`)
  },
}))
vi.mock('../MonitorPanel', () => ({ default: () => <div data-testid="resources" /> }))

import MonitorTabs from './MonitorTabs'

afterEach(() => { cleanup(); vi.clearAllMocks() })

const requestRow = {
  id: 1, at: '2026-09-24T10:00:00', method: 'GET', path: '/api/x', status: 500,
  duration_ms: 1200, user_id: 1, user_login: 'jan', ip: '1.1.1.1', request_id: 'r1', error: 'boom',
}
const trafficRow = { at: '2026-09-24T10:00:00', total: 5, c4xx: 1, c5xx: 1, avg_ms: 100 }

describe('MonitorTabs — Żądania', () => {
  it('woła requests + traffic po otwarciu, pokazuje wiersz 5xx, rozwija błąd, filtruje po statusie', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url.startsWith('/api/admin/logs/requests'))
        return Promise.resolve({ total: 1, items: [requestRow] })
      if (url.startsWith('/api/admin/logs/traffic'))
        return Promise.resolve([trafficRow])
      return Promise.resolve({})
    })
    render(<MonitorTabs />)
    fireEvent.click(screen.getByRole('button', { name: 'logTabRequests' }))

    await waitFor(() => expect(apiGet).toHaveBeenCalledWith(
      expect.stringMatching(/^\/api\/admin\/logs\/requests/)))
    expect(apiGet).toHaveBeenCalledWith('/api/admin/logs/traffic?hours=24')

    const statusCell = await screen.findByText('500')
    expect(statusCell.className).toContain('log-5xx')

    fireEvent.click(statusCell.closest('tr')!)
    expect(await screen.findByText('boom')).toBeTruthy()

    apiGet.mockClear()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '5xx' } })
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith(
      expect.stringContaining('status=5xx')))
  })
})

describe('MonitorTabs — Zadania tła', () => {
  it('kafelek ok:false oznaczony błędem, klik w historię pokazuje detail', async () => {
    const job = { job: 'sync', fn: 'run', started_at: '2026-09-24T10:00:00', duration_ms: 5, ok: false, detail: 'oops' }
    apiGet.mockImplementation((url: string) => {
      if (url.startsWith('/api/admin/logs/jobs')) return Promise.resolve({ latest: [job], history: [job] })
      return Promise.resolve({})
    })
    render(<MonitorTabs />)
    fireEvent.click(screen.getByRole('button', { name: 'logTabJobs' }))

    const tile = await screen.findByText('sync/run', { selector: 'span' })
    expect(tile.closest('.log-tile')?.className).toContain('log-tile-err')

    const historyRow = screen.getByText('sync/run', { selector: 'td' })
    fireEvent.click(historyRow.closest('tr')!)
    expect(await screen.findByText('oops')).toBeTruthy()
  })
})

describe('MonitorTabs — wyścig zapytań (race guard)', () => {
  it('starsza odpowiedź rozwiązana po nowszej nie nadpisuje wyświetlonych danych', async () => {
    let call = 0
    let resolveFirst: (v: unknown) => void = () => {}
    let resolveSecond: (v: unknown) => void = () => {}
    apiGet.mockImplementation((url: string) => {
      if (url.startsWith('/api/admin/logs/requests')) {
        call += 1
        return call === 1
          ? new Promise(res => { resolveFirst = res })
          : new Promise(res => { resolveSecond = res })
      }
      if (url.startsWith('/api/admin/logs/traffic')) return Promise.resolve([])
      return Promise.resolve({})
    })
    render(<MonitorTabs />)
    fireEvent.click(screen.getByRole('button', { name: 'logTabRequests' }))
    await waitFor(() => expect(call).toBe(1))

    fireEvent.click(screen.getByRole('button', { name: 'logRefresh' }))
    await waitFor(() => expect(call).toBe(2))

    // nowsza odpowiedź przychodzi pierwsza, starsza dociera z opóźnieniem
    resolveSecond({ total: 1, items: [{ ...requestRow, id: 2, path: '/api/newer' }] })
    await screen.findByText('/api/newer')
    resolveFirst({ total: 1, items: [{ ...requestRow, id: 1, path: '/api/older' }] })
    await new Promise(r => setTimeout(r, 0))

    expect(screen.getByText('/api/newer')).toBeTruthy()
    expect(screen.queryByText('/api/older')).toBeNull()
  })
})

describe('MonitorTabs — wykres ruchu', () => {
  it('pojedynczy kubełek renderuje cienki słupek, dużo węższy niż wykres', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url.startsWith('/api/admin/logs/requests')) return Promise.resolve({ total: 0, items: [] })
      if (url.startsWith('/api/admin/logs/traffic')) return Promise.resolve([trafficRow])
      return Promise.resolve({})
    })
    const { container } = render(<MonitorTabs />)
    fireEvent.click(screen.getByRole('button', { name: 'logTabRequests' }))
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/admin/logs/traffic?hours=24'))

    const rect = await waitFor(() => {
      const r = container.querySelector('svg rect')
      if (!r) throw new Error('brak słupka')
      return r
    })
    const width = Number(rect.getAttribute('width'))
    expect(width).toBeGreaterThan(0)
    expect(width).toBeLessThan(60)   // wykres ma 600 jednostek szerokości — słupek dużo węższy
  })
})

describe('MonitorTabs — puste/nieoczekiwane odpowiedzi', () => {
  it('{} dla każdej podzakładki — brak wyjątku, pusty stan', async () => {
    apiGet.mockResolvedValue({})
    render(<MonitorTabs />)

    fireEvent.click(screen.getByRole('button', { name: 'logTabRequests' }))
    expect(await screen.findAllByText('logEmpty')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'logTabJobs' }))
    expect(await screen.findAllByText('logEmpty')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'logTabClientErrors' }))
    expect(await screen.findAllByText('logEmpty')).toBeTruthy()
  })
})
