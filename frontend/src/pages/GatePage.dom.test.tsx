// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { DICTS, LANGS } from '../i18n'

// W10 — parytet słowników: klucze gate*/avp*/ul*/huInv*/staff* w pl, en i pt
describe('W10 — parytet słowników', () => {
  it('każdy nowy klucz istnieje w pl, en i pt', () => {
    const keys = Object.keys(DICTS.pl).filter(k =>
      /^(gate|avp|ul|huInv|staff)/.test(k) || k === 'qrPrintLabel')
    expect(keys.length).toBeGreaterThan(20)
    for (const lang of LANGS) {
      const missing = keys.filter(k => !DICTS[lang][k])
      expect(missing, `brakuje w ${lang}: ${missing.join(', ')}`).toEqual([])
    }
  })
})

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../api', () => ({
  api: { get: apiGet, post: apiPost, upload: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('../App', () => ({ useUser: () => ({ role: 'warehouse' }) }))
vi.mock('../feedback', async (orig) => ({
  ...(await orig() as object), useToast: () => ({ showToast: vi.fn() }),
}))

afterEach(() => { cleanup(); apiGet.mockReset(); apiPost.mockReset() })

const item = {
  id: 7, container_no: 'MSDU0806613', truck_no: 'WGM 1234A', trailer_no: 'WGM 5678B',
  driver_name: 'Jan Kierowca', warehouse_id: 1, warehouse: 'DLT',
  notify_date: '2026-09-18', eta: null, status: 'AWIZOWANY',
  driver_arrived_at: null, checked_in_at: null,
}

describe('GatePage (#60)', () => {
  it('renderuje auto z nr rej. i przyciskiem Przyjechał; check-in strzela do API', async () => {
    apiGet.mockResolvedValue({ day: '2026-09-18', items: [item] })
    apiPost.mockResolvedValue({ status: 'ok', already: false })
    const { default: GatePage } = await import('./GatePage')
    render(<MemoryRouter><GatePage /></MemoryRouter>)

    expect(await screen.findByText('MSDU0806613')).toBeTruthy()
    expect(screen.getByText(/WGM 1234A/)).toBeTruthy()
    const btn = screen.getByRole('button', { name: /Przyjechał/ })
    fireEvent.click(btn)
    await screen.findByText('MSDU0806613')   // po reload
    expect(apiPost).toHaveBeenCalledWith('/api/gate/7/checkin', {})
  })

  it('„Spóźnienie”: godzina od kierowcy (telefon) trafia do API bramy', async () => {
    apiGet.mockResolvedValue({ day: '2026-09-18', items: [item] })
    apiPost.mockResolvedValue({ status: 'ok' })
    vi.spyOn(window, 'prompt').mockReturnValue('14:30')
    const { default: GatePage } = await import('./GatePage')
    render(<MemoryRouter><GatePage /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: /Spóźnienie/ }))
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/gate/7/delay', { eta_time: '14:30' }))
  })

  it('odnotowane auto pokazuje plakietkę zamiast przycisku', async () => {
    apiGet.mockResolvedValue({
      day: '2026-09-18',
      items: [{ ...item, checked_in_at: '2026-09-18T06:12:00' }],
    })
    const { default: GatePage } = await import('./GatePage')
    render(<MemoryRouter><GatePage /></MemoryRouter>)
    expect(await screen.findByText(/Odnotowano na bramie/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Przyjechał/ })).toBeNull()
  })

  it('pusty dzień pokazuje komunikat', async () => {
    apiGet.mockResolvedValue({ day: '2026-09-18', items: [] })
    const { default: GatePage } = await import('./GatePage')
    render(<MemoryRouter><GatePage /></MemoryRouter>)
    expect(await screen.findByText('Brak spodziewanych aut na dziś')).toBeTruthy()
  })

  it('D9: magazyn zmienia etap rampy (drugi wymiar obok statusu)', async () => {
    apiGet.mockResolvedValue({ day: '2026-09-18', items: [{ ...item, ramp_stage: 'PODSTAWIONY' }] })
    apiPost.mockResolvedValue({ ramp_stage: 'ROZLADOWANY' })
    const { default: GatePage } = await import('./GatePage')
    render(<MemoryRouter><GatePage /></MemoryRouter>)
    const select = await screen.findByRole('combobox', { name: 'Etap rampy' }) as HTMLSelectElement
    expect(select.value).toBe('PODSTAWIONY')
    fireEvent.change(select, { target: { value: 'ROZLADOWANY' } })
    expect(apiPost).toHaveBeenCalledWith('/api/containers/7/ramp-stage', { stage: 'ROZLADOWANY' })
  })

  it('C29: widoczna etykieta etapu, opcja „Przed rampą”, bez samotnego „—” przy braku nr auta', async () => {
    apiGet.mockResolvedValue({ day: '2026-09-18', items: [{ ...item, truck_no: '', trailer_no: '' }] })
    const { default: GatePage } = await import('./GatePage')
    const { container } = render(<MemoryRouter><GatePage /></MemoryRouter>)
    const select = await screen.findByRole('combobox', { name: 'Etap rampy' }) as HTMLSelectElement
    expect(select.closest('label')!.textContent).toContain('Etap rampy')   // widoczna, nie tylko aria-label
    expect(select.options[0].textContent).toBe('Przed rampą')
    expect(container.querySelector('.gate-truck')).toBeNull()
  })
})
