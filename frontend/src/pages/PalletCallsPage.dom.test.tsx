// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { DICTS, LANGS } from '../i18n'

// TOP 10 audytu — i18n/spójność: klucze pc*/an* muszą istnieć we wszystkich językach,
// a surowe statusy (draft/sent/...) mają być tłumaczone.
describe('TOP 10 — parytet słowników', () => {
  it('każdy klucz pc*/an* istnieje w pl, en i pt', () => {
    const keys = Object.keys(DICTS.pl).filter(k => k.startsWith('pc') || k.startsWith('an'))
    expect(keys.length).toBeGreaterThan(20)
    for (const lang of LANGS) {
      const missing = keys.filter(k => !DICTS[lang][k])
      expect(missing, `brakuje w ${lang}: ${missing.join(', ')}`).toEqual([])
    }
  })
})

// UX-026: filtr „tylko pilne” i akcja wypełniania pilnymi nie mogą mieć tej samej etykiety
describe('UX-026 — filtr vs akcja', () => {
  it('etykieta akcji pcOnlyUrgent różni się od filtra pcUrgentOnly w każdym języku', () => {
    for (const lang of LANGS) {
      expect(DICTS[lang].pcOnlyUrgent.toLowerCase()).not.toBe(DICTS[lang].pcUrgentOnly.toLowerCase())
    }
  })
})

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({
  api: { get: apiGet, post: vi.fn(), upload: vi.fn() },
  downloadFile: vi.fn(), errorMessage: (e: unknown) => String(e),
}))
vi.mock('../App', () => ({ useUser: () => ({ role: 'viewer' }) }))
vi.mock('../feedback', async (orig) => ({
  ...(await orig() as object), useToast: () => ({ showToast: vi.fn() }),
}))

afterEach(() => { cleanup(); apiGet.mockReset() })

describe('TOP 10 — statusy wywołań tłumaczone', () => {
  it('status "draft" renderuje się jako etykieta (pl: Szkic), nie surowo', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/pallet-calls/analysis'))
        return Promise.resolve({ items: [], total: 0, fetched_at: null, discrepancies: [] })
      if (path === '/api/pallet-calls')
        return Promise.resolve([{
          id: 1, number: 'W-1', status: 'draft', needed_by: null,
          notes: '', created_at: '', sent_at: null, lines: [],
        }])
      return Promise.reject(new Error('x'))
    })
    const { default: PalletCallsPage } = await import('./PalletCallsPage')
    render(<PalletCallsPage />)

    expect(await screen.findByText('Szkic')).toBeTruthy()
    await waitFor(() => expect(screen.queryByText('draft')).toBeNull())
  })
})
