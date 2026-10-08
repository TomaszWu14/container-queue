// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { act } from 'react'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
import { describe, expect, it, vi } from 'vitest'
import ContainerTimeline from './pages/tracking/ContainerTimeline'
import { api } from './api'

vi.mock('./api', () => ({ api: { get: vi.fn().mockResolvedValue([
  { kind: 'carrier', code: 'DEPART', title: 'Vessel departure',
    location: 'Ningbo', at: '2025-12-02T08:00:00', estimated: false, source: 'armator' },
  { kind: 'planned', code: 'ETA', title: 'ETA', location: '',
    at: '2099-01-10T00:00:00', estimated: true, source: 'system' },
]) } }))

describe('ContainerTimeline', () => {
  it('renderuje wpisy, tłumaczy znane kody i oznacza szacowane', async () => {
    render(<ContainerTimeline containerId={1} refreshKey={0} />)
    expect(await screen.findByText(/Wyjście z portu/)).toBeTruthy()   // ev_DEPART pl
    expect(screen.getByText(/szacowane/)).toBeTruthy()
  })

  it('dla nieznanego kodu przewoźnika renderuje tytuł z backendu, nie surowy klucz', async () => {
    vi.mocked(api.get).mockResolvedValueOnce([
      { kind: 'carrier', code: 'XX_UNKNOWN', title: 'Jakiś opis',
        location: '', at: '2025-12-02T08:00:00', estimated: false, source: 'armator' },
    ])
    render(<ContainerTimeline containerId={2} refreshKey={0} />)
    expect(await screen.findByText('Jakiś opis')).toBeTruthy()
    expect(screen.queryByText(/ev_XX_UNKNOWN/)).toBeNull()
  })

  // regresja: `done` liczone raz na render zamrażało „teraz" na moment wejścia —
  // strona otwarta cały dzień nie domykała wpisów, które w międzyczasie minęły
  it('domyka wpis, który minął przy otwartej stronie', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T09:59:00Z'))
    vi.mocked(api.get).mockResolvedValueOnce([
      { kind: 'carrier', code: 'DEPART', title: 'Wyjście', location: '',
        at: '2026-01-01T10:00:00Z', estimated: false, source: 'armator' },
    ])
    const { container } = render(<ContainerTimeline containerId={3} refreshKey={0} />)
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(container.querySelector('li.done')).toBeNull()

    await act(async () => { await vi.advanceTimersByTimeAsync(120_000) })
    expect(container.querySelector('li.done')).toBeTruthy()
    vi.useRealTimers()
  })
})
