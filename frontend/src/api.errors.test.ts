// TOP 3 audytu UX: walidacje 422 pydantic nie mogą wyciekać po angielsku do UI
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, detailMessage, httpMessage } from './api'

describe('detailMessage — tłumaczenie detail z backendu', () => {
  it('string detail przechodzi bez zmian (backend pisze po polsku)', () => {
    expect(detailMessage('Nie znaleziono kontenerów.', 'x')).toBe('Nie znaleziono kontenerów.')
  })

  it('brak/nieznany detail → fallback', () => {
    expect(detailMessage(undefined, 'Błąd 500')).toBe('Błąd 500')
    expect(detailMessage({ some: 'obj' }, 'Błąd 500')).toBe('Błąd 500')
  })

  it('pydantic 422: typowe komunikaty po polsku, z nazwą pola', () => {
    const detail = [
      { loc: ['body', 'email'], msg: 'value is not a valid email address' },
      { loc: ['body', 'count'], msg: 'value is not a valid integer' },
      { loc: ['body', 'login'], msg: 'field required' },
    ]
    const msg = detailMessage(detail, 'x')
    expect(msg).toContain('email: nieprawidłowy adres e-mail')
    expect(msg).toContain('count: wymagana liczba całkowita')
    expect(msg).toContain('login: pole wymagane')
    expect(msg).not.toMatch(/field required|valid integer|valid email/)
  })

  it('limity długości z liczbą z komunikatu (pydantic v2)', () => {
    const detail = [{ loc: ['body', 'password'], msg: 'String should have at least 8 characters' }]
    expect(detailMessage(detail, 'x')).toContain('password: za krótkie (min. 8 znaków)')
  })

  it('nieznany angielski msg → ogólny polski, bez wycieku', () => {
    const detail = [{ loc: ['body', 'weird'], msg: 'some cryptic english validation text' }]
    const msg = detailMessage(detail, 'x')
    expect(msg).toContain('weird: nieprawidłowa wartość')
    expect(msg).not.toContain('cryptic')
  })

  it('własny walidator (ValueError, np. ISO 6346) — pokazuje realny komunikat zamiast generyka', () => {
    const detail = [{
      loc: ['body', 'container_number'],
      msg: 'Value error, Błędna cyfra kontrolna ISO 6346 — dla MSDU0806615 powinna być 8.',
    }]
    const msg = detailMessage(detail, 'x')
    expect(msg).toContain('container_number: Błędna cyfra kontrolna ISO 6346 — dla MSDU0806615 powinna być 8.')
    expect(msg).not.toContain('nieprawidłowa wartość')
  })
})

// Sieć down/DNS: fetch rzuca TypeError (EN) — klient musi go zamienić na polski ApiError(0)
describe('request — błąd sieci', () => {
  const orig = globalThis.fetch
  afterEach(() => { globalThis.fetch = orig })

  it('odrzucony fetch → polski ApiError(0), bez angielskiego „Failed to fetch"', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(api.get('/api/x')).rejects.toMatchObject({
      status: 0, message: expect.stringContaining('Brak połączenia'),
    })
  })
})

// audyt UI C2: „Internal Server Error” po angielsku nie może trafiać do banera/toastu
describe('httpMessage — domyślne teksty HTTP po polsku', () => {
  it('5xx z angielskim detail albo bez treści → polski komunikat z kodem', () => {
    expect(httpMessage(500, 'Internal Server Error')).toBe(
      'Serwer nie odpowiedział poprawnie (błąd 500). Spróbuj ponownie za chwilę.')
    expect(httpMessage(502, 'Błąd 502')).toContain('błąd 502')
    expect(httpMessage(403, 'Forbidden')).toBe('Brak dostępu do tych danych (błąd 403).')
    expect(httpMessage(429, 'Too Many Requests')).toContain('odczekaj chwilę')
  })

  it('własny komunikat backendu przechodzi bez zmian', () => {
    expect(httpMessage(503, 'Integracja SAP niedostępna')).toBe('Integracja SAP niedostępna')
    expect(httpMessage(409, 'Agencja nie ma adresu e-mail.')).toBe('Agencja nie ma adresu e-mail.')
  })
})
