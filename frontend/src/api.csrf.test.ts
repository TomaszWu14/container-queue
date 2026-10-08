// SEC-004: każde żądanie frontu do /api niesie X-Requested-With — bez niego backend odrzuca
// zapis z ciasteczkiem sesji, gdy Origin nie jest naszym adresem (np. proxy Vite w dev)
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, login, logoutRequest } from './api'

const sentHeaders = (mock: ReturnType<typeof vi.fn>) =>
  mock.mock.calls.map(([, init]) => (init?.headers ?? {}) as Record<string, string>)

describe('nagłówek CSRF (SEC-004)', () => {
  const orig = globalThis.fetch
  afterEach(() => { globalThis.fetch = orig })

  it('wspólny klient, upload, logowanie i wylogowanie wysyłają X-Requested-With', async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })))
    globalThis.fetch = fetchMock
    await api.get('/api/x')
    await api.post('/api/x', { a: 1 })
    await api.del('/api/x')
    await api.upload('/api/x', new File(['a'], 'a.csv'))
    await login('admin', 'haslo')
    await logoutRequest()
    const headers = sentHeaders(fetchMock)
    expect(headers).toHaveLength(6)
    for (const h of headers) expect(h['X-Requested-With']).toBe('XMLHttpRequest')
    // multipart: boundary ustawia przeglądarka — nie nadpisujemy Content-Type
    expect(headers[3]['Content-Type']).toBeUndefined()
  })
})
