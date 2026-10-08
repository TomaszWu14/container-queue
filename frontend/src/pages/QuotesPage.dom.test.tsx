// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { TransportJob } from '../types'
import QuotesPage from './QuotesPage'

// TOP 9 audytu — wybór oferty przez modal spójny z resztą (koniec window.prompt).
vi.mock('../i18n', () => ({
  useT: () => (key: string) => ({
    quoteChoose: 'Wybierz', quoteChoiceReason: 'Powód wyboru', cancel: 'Anuluj',
  } as Record<string, string>)[key] ?? key,
}))
vi.mock('../App', () => ({ useUser: () => ({ role: 'admin' }) }))

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../api', () => ({
  api: { get: apiGet, post: apiPost },
  downloadFile: vi.fn(), errorMessage: (e: unknown) => String(e),
}))

const job = {
  id: 1, number: 'TJ-1', status: 'WYSLANE',
  pickup_location: 'A', delivery_location: 'B', sent_at: null, response_deadline: null,
  response_hours: 48, scfi_index: null, note: null, container_count: 0, containers: [],
  kpi: { invited: 1, responded: 1, response_rate: 100, expired: 0, deadline_passed: false },
  quotes: [{
    id: 9, forwarder_name: 'Speed', amount: 100, currency: 'USD', revised_amount: null,
    score: null, recommended: false, carrier_name: null, etd: null, eta: null,
    transit_time_days: null, no_equipment: false, can_roll_booking: false,
    status: 'WYCENIONA', note: null, submitted_at: null,
  }],
} as unknown as TransportJob

afterEach(() => { cleanup(); apiGet.mockReset(); apiPost.mockReset() })

describe('TOP 9 — wybór oferty przez modal', () => {
  it('nierekomendowana oferta: modal z wymaganym powodem, potem POST z reason', async () => {
    apiGet.mockResolvedValue([job])
    apiPost.mockResolvedValue(job)
    render(<QuotesPage />)

    const chooseBtn = await screen.findByText('Wybierz')
    fireEvent.click(chooseBtn)

    // modal się pokazał; przycisk potwierdzenia zablokowany bez powodu
    const dialog = document.querySelector('.modal') as HTMLElement
    expect(dialog).toBeTruthy()
    const confirm = within(dialog).getByRole('button', { name: 'Wybierz' }) as HTMLButtonElement
    expect(confirm.disabled).toBe(true)

    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'tańszy' } })
    expect(confirm.disabled).toBe(false)
    fireEvent.click(confirm)

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/transport-jobs/1/choose', { quote_id: 9, reason: 'tańszy' }))
  })
})
