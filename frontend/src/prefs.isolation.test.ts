// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPut } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPut: vi.fn().mockResolvedValue({}),
}))
vi.mock('./api', () => ({ api: { get: apiGet, put: apiPut } }))

import { pullPrefs } from './prefs'

afterEach(() => { localStorage.clear(); vi.clearAllMocks() })

describe('pullPrefs — izolacja per user', () => {
  it('czyści syncowalne klucze poprzedniego usera przed zasiewem z serwera', async () => {
    localStorage.setItem('queueViews', '[{"name":"widok-usera-A"}]')
    localStorage.setItem('timporye_cols_wide_acme', '["statek"]')
    localStorage.setItem('timporye_lang', 'pl') // nie-syncowalny — ma zostać
    apiGet.mockResolvedValue({ queueRowHeight: 'compact' })

    await pullPrefs()

    expect(localStorage.getItem('queueViews')).toBeNull()
    expect(localStorage.getItem('timporye_cols_wide_acme')).toBeNull()
    expect(localStorage.getItem('queueRowHeight')).toBe('compact')
    expect(localStorage.getItem('timporye_lang')).toBe('pl')
  })

  it('offline/błąd serwera: lokalne ustawienia zostają nietknięte', async () => {
    localStorage.setItem('queueViews', '[{"name":"lokalny"}]')
    apiGet.mockRejectedValue(new Error('offline'))

    await pullPrefs()

    expect(localStorage.getItem('queueViews')).toBe('[{"name":"lokalny"}]')
  })
})
