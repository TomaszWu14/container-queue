import { afterEach, expect, it, vi } from 'vitest'
import { api } from './api'
import { totalOf } from './listTotal'

afterEach(() => vi.unstubAllGlobals())

it('api.get zapamiętuje X-Total-Count przy liście (audyt DATA-002)', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([{ id: 1 }]),
    { status: 200, headers: { 'X-Total-Count': '7' } })))
  const data = await api.get<unknown[]>('/api/containers?limit=1')
  expect(totalOf(data)).toBe(7)
})

it('bez nagłówka — brak sumy', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('[]', { status: 200 })))
  expect(totalOf(await api.get<unknown[]>('/api/x'))).toBeNull()
})
