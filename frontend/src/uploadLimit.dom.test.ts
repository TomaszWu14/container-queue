// @vitest-environment jsdom
// Za duży plik odrzucony PRZED wysłaniem (zamiast minut uploadu i 413 z backendu).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import { setUploadLimitMb } from './uploadLimit'

const orig = globalThis.fetch
afterEach(() => { globalThis.fetch = orig; setUploadLimitMb(25) })

const fileOf = (mb: number, name = 'skan.pdf') =>
  new File([new Uint8Array(Math.round(mb * 1024 * 1024))], name)

describe('limit wielkości pliku', () => {
  it('plik ponad limit → błąd po polsku, bez żądania do serwera', async () => {
    const fetchSpy = vi.fn()
    globalThis.fetch = fetchSpy as typeof fetch
    setUploadLimitMb(1)
    await expect(api.upload('/api/x', fileOf(1.5))).rejects.toThrow(/skan\.pdf.*za duży.*1 MB/)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('plik w limicie idzie normalnie; limit z ui-config ignoruje śmieci', async () => {
    globalThis.fetch = vi.fn(async () => new Response('{}', { status: 200 })) as typeof fetch
    setUploadLimitMb(undefined)          // brak pola w ui-config → zostaje poprzedni (25)
    await expect(api.upload('/api/x', fileOf(0.5))).resolves.toEqual({})
  })
})
