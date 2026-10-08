// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AvizoProposalsPage, { allowedActions } from './AvizoProposalsPage'

const get = vi.fn()
const post = vi.fn()
vi.mock('../api', () => ({
  api: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('./admin/shared', () => ({ useForwarders: () => [{ id: 3, name: 'FW' }] }))

afterEach(() => { cleanup(); get.mockReset(); post.mockReset() })

const ROW = { id: 11, status: 'CONFIRMED_BY_FORWARDER', forwarder_id: 3, forwarder: 'FW',
  company: 'ACME', containers: ['MSCU1234571', 'TGHU0000001'], created_at: '2026-09-20T10:00:00',
  reject_comment: '', note: '',
  last_mail: { status: 'failed', stage: 1, error: 'SMTP down', sent_at: null } }
const DETAIL = { ...ROW,
  items: [{ container_id: 7, container_no: 'MSCU1234571', notify_date: '2026-10-05', slot_time: '',
    driver_submitted: false, answer: { decision: 'date_change', proposed_date: '2026-10-09',
      slot_time: '11:00', comment: 'later please', submitted_at: null } }],
  tokens: [{ id: 1, stage: 1 }],
  mails: [{ id: 1, stage: 1, kind: 'stage1', recipients: 'fw@x.pl', cc: '', backend: 'smtp',
    status: 'failed', attempts: 3, error: 'SMTP down', sent_at: null }] }

function mockGet() {
  get.mockImplementation(async (path: string) => {
    if (path.startsWith('/api/avizo-requests/11')) return DETAIL
    if (path.startsWith('/api/avizo-requests')) return [ROW]
    return []   // legacy propozycje — brak → sekcja ukryta
  })
}

const renderPage = () => render(<MemoryRouter><AvizoProposalsPage /></MemoryRouter>)

describe('allowedActions — lustro maszyny stanów', () => {
  it.each([
    ['CONFIRMED_BY_FORWARDER', ['approve', 'reject', 'cancel'], null],
    ['SENT_STAGE1', ['revoke', 'resend', 'cancel'], 1],
    ['SENT_STAGE2', ['revoke', 'resend', 'cancel'], 2],
    ['DRIVERS_SUBMITTED', [], null],
    ['CLOSED', [], null],
  ])('%s', (status, actions, stage) => {
    expect(allowedActions({ status, tokens: [] })).toEqual({ actions, resendStage: stage })
  })
  it('EXPIRED → ponowna wysyłka etapu ostatniego tokenu', () => {
    expect(allowedActions({ status: 'EXPIRED', tokens: [{ id: 1, stage: 1 }, { id: 2, stage: 2 }] })
      .resendStage).toBe(2)
  })
})

describe('AvizoProposalsPage — panel Awizacje', () => {
  it('lista → szczegóły z odpowiedziami i logiem maili; filtr statusu idzie w query', async () => {
    mockGet()
    renderPage()
    fireEvent.click(await screen.findByText('ACME'))
    expect(await screen.findByText('later please')).toBeTruthy()
    expect(screen.getByText(/×3: SMTP down/)).toBeTruthy()
    expect(screen.queryByText('avrRevoke')).toBeNull()   // niedozwolone w tym statusie

    fireEvent.change(screen.getByLabelText('status'), { target: { value: 'EXPIRED' } })
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/avizo-requests?status=EXPIRED'))
  })

  it('odrzucenie wymaga komentarza (inline potwierdzenie, bez window.confirm)', async () => {
    mockGet()
    post.mockResolvedValue({ ...DETAIL, status: 'SENT_STAGE1' })
    renderPage()
    fireEvent.click(await screen.findByText('ACME'))
    fireEvent.click(await screen.findByText('avrReject'))
    const yes = screen.getByText('avrYes') as HTMLButtonElement
    expect(yes.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('avrRejectComment'), { target: { value: 'wrong slot' } })
    fireEvent.click(yes)
    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/api/avizo-requests/11/reject', { comment: 'wrong slot' }))
  })
})
