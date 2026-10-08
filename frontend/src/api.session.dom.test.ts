// @vitest-environment jsdom
// Sesja wygasła: 401 także po odświeżeniu → globalne zdarzenie (App wraca do logowania)
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import { SESSION_EXPIRED_EVENT } from './sessionEvents'

const orig = globalThis.fetch
const seen = vi.fn()
window.addEventListener(SESSION_EXPIRED_EVENT, seen)
afterEach(() => { globalThis.fetch = orig; seen.mockClear() })

const res = (status: number, body: unknown = { detail: 'x' }) =>
  new Response(JSON.stringify(body), { status })

describe('request — sesja wygasła', () => {
  it('401 + nieudany refresh → zdarzenie timporye:session-expired', async () => {
    globalThis.fetch = vi.fn(async () => res(401)) as typeof fetch
    await expect(api.get('/api/containers')).rejects.toMatchObject({ status: 401 })
    expect(seen).toHaveBeenCalledTimes(1)
  })

  it('401 → udany refresh → 200: brak zdarzenia', async () => {
    let calls = 0
    globalThis.fetch = vi.fn(async (url: RequestInfo | URL) => {
      if (String(url).includes('/auth/refresh')) return res(200, {})
      return ++calls === 1 ? res(401) : res(200, [])
    }) as typeof fetch
    await expect(api.get('/api/containers')).resolves.toEqual([])
    expect(seen).not.toHaveBeenCalled()
  })

  it('403 to nie wygaśnięcie sesji', async () => {
    globalThis.fetch = vi.fn(async () => res(403)) as typeof fetch
    await expect(api.get('/api/containers')).rejects.toMatchObject({ status: 403 })
    expect(seen).not.toHaveBeenCalled()
  })
})
