// Autoryzacja oparta o cookies HttpOnly ustawiane przez backend — tokeny nie są
// przechowywane w localStorage (ochrona przed kradzieżą przez XSS).
import { CSRF_HEADERS } from './csrf'
import { rememberTotal } from './listTotal'
import { SESSION_EXPIRED_EVENT } from './sessionEvents'
import { assertUploadSize } from './uploadLimit'

// sygnał dla DeployWatch (ekran wdrożenia); poza przeglądarką (testy w Node) — nic
const serverUnreachable = () => {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('timporye:server-unreachable'))
}

const sessionExpired = () => {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// pydantic 422: `detail` to lista {loc, msg} z komunikatami po ANGIELSKU ("field
// required") — tłumaczymy typowe przypadki, reszta dostaje ogólny polski komunikat,
// żeby techniczny angielski nie trafiał do <p class="error"> w całej aplikacji.
const PYDANTIC_PL: Array<[RegExp, string]> = [
  [/field required|^missing$/i, 'pole wymagane'],
  [/valid integer/i, 'wymagana liczba całkowita'],
  [/valid number/i, 'wymagana liczba'],
  [/valid email/i, 'nieprawidłowy adres e-mail'],
  [/valid date/i, 'nieprawidłowa data'],
  [/at least (\d+) characters/i, 'za krótkie (min. $1 znaków)'],
  [/at most (\d+) characters/i, 'za długie (maks. $1 znaków)'],
]

function validationItem(d: { loc?: unknown[]; msg?: string }): string {
  const field = Array.isArray(d.loc)
    ? d.loc.filter(p => p !== 'body' && typeof p === 'string').join('.') : ''
  const raw = d.msg ?? ''
  const hit = PYDANTIC_PL.find(([re]) => re.test(raw))
  let text: string
  if (hit) {
    text = hit[1].replace('$1', raw.match(hit[0])?.[1] ?? '')
  } else if (/^value error,\s*/i.test(raw)) {
    // własny walidator (ValueError) — komunikat już po polsku, pokaż go zamiast gubić
    text = raw.replace(/^value error,\s*/i, '')
  } else {
    text = 'nieprawidłowa wartość'
  }
  return field ? `${field}: ${text}` : text
}

export function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  // błąd z kodem maszynowym: {code, message}
  if (detail && typeof detail === 'object' && 'message' in detail) return String(detail.message)
  if (Array.isArray(detail))
    return `Nieprawidłowe dane formularza — ${detail.map(validationItem).join('; ')}`
  return fallback
}

// Domyślne (angielskie) teksty Starlette/FastAPI i proxy — zamiast nich polski komunikat
// z kodem jako szczegółem (audyt UI C2). Własne `detail` backendu przechodzą bez zmian.
const HTTP_DEFAULT_EN = new Set(['Internal Server Error', 'Bad Gateway', 'Service Unavailable',
  'Gateway Timeout', 'Not Found', 'Forbidden', 'Not authenticated', 'Unauthorized',
  'Too Many Requests', 'Method Not Allowed'])

export function httpMessage(status: number, message: string): string {
  if (!HTTP_DEFAULT_EN.has(message) && message !== `Błąd ${status}`) return message
  if (status >= 500) return `Serwer nie odpowiedział poprawnie (błąd ${status}). Spróbuj ponownie za chwilę.`
  if (status === 429) return 'Za dużo zapytań naraz — odczekaj chwilę i spróbuj ponownie.'
  if (status === 404) return 'Nie znaleziono danych (błąd 404).'
  if (status === 401 || status === 403) return `Brak dostępu do tych danych (błąd ${status}).`
  return message
}

let refreshing: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  // pojedyncze odświeżenie współdzielone przez równoległe żądania
  refreshing ??= fetch('/api/auth/refresh', { method: 'POST', headers: CSRF_HEADERS })
    .then(response => response.ok)
    .catch(() => false)
    .finally(() => { refreshing = null })
  return refreshing
}

async function request<T>(path: string, options: RequestInit = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = {
    ...CSRF_HEADERS,
    ...(options.headers as Record<string, string> | undefined),
  }
  // FormData ustawia własny multipart boundary — nie nadpisujemy Content-Type
  if (options.body && !headers['Content-Type'] && !(options.body instanceof FormData))
    headers['Content-Type'] = 'application/json'

  // sieć down / DNS / timeout: fetch rzuca TypeError (po angielsku) albo zawiesza żądanie
  // w nieskończoność (blokując formularze z `busy`). Tłumaczymy na polski ApiError(0) i
  // dokładamy limit czasu (feature-detect AbortSignal.timeout — brak → bez limitu).
  let response: Response
  try {
    response = await fetch(path, {
      ...options, headers,
      signal: options.signal ?? AbortSignal.timeout?.(30_000),
    })
  } catch (err) {
    serverUnreachable()   // DeployWatch: może trwa wdrożenie
    const timedOut = err instanceof DOMException && err.name === 'TimeoutError'
    throw new ApiError(0, timedOut
      ? 'Przekroczono czas oczekiwania na serwer'
      : 'Brak połączenia z serwerem — sprawdź internet')
  }
  if (response.status === 401 && !retried && (await tryRefresh())) {
    return request<T>(path, options, true)
  }
  // 401 mimo (próby) odświeżenia = sesja wygasła: App wraca do ekranu logowania (z tym
  // samym adresem) zamiast losowych błędów „Brak dostępu” i dalszego odpytywania w tle
  if (response.status === 401) sessionExpired()
  if (!response.ok) {
    // 502/503/504 = proxy bez aplikacji (wdrożenie / restart) → DeployWatch sprawdza /api/health
    if (response.status >= 502 && response.status <= 504) serverUnreachable()
    let message = `Błąd ${response.status}`
    try {
      const body = await response.json()
      message = detailMessage(body.detail, message)
    } catch { /* treść nie-JSON */ }
    throw new ApiError(response.status, httpMessage(response.status, message))
  }
  if (response.status === 204) return undefined as T
  const data = await response.json()
  rememberTotal(data, response.headers.get('X-Total-Count'))
  return data as T
}

const UPLOAD_TIMEOUT_MS = 180_000


export const api = {
  // signal: anulowanie (np. podpowiedzi wyszukiwarki) — zastępuje domyślny limit 30 s
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  // upload przez wspólny klient: obsługa 401→refresh→retry i błędów (response.ok)
  // `file` może być listą — multipart z powtórzonym polem (faktury: 1..n PDF-ów)
  upload: <T>(path: string, file: File | File[], field = 'file',
              extra?: Record<string, string>) => {
    const files = Array.isArray(file) ? file : [file]
    try { assertUploadSize(files) } catch (err) { return Promise.reject(err) }
    const data = new FormData()
    for (const one of files) data.append(field, one)
    for (const [k, v] of Object.entries(extra ?? {})) data.append(k, v)
    // importy z SAP (EKKO 18 tys. / EKPO 47 tys. wierszy) na 1-rdzeniowym serwerze trwają
    // dłużej niż ogólne 30 s (2026-09-29: „Przekroczono czas oczekiwania” przy EKKO) — upload
    // czeka do UPLOAD_TIMEOUT_MS; ciężkie importy i tak idą w tle (dane materiałowe SharePoint)
    return request<T>(path, { method: 'POST', body: data,
                              signal: AbortSignal.timeout?.(UPLOAD_TIMEOUT_MS) })
  },
}

// jednolity komunikat błędu (ApiError niesie sensowny message; reszta → String)
export const errorMessage = (err: unknown): string =>
  err instanceof Error ? err.message : String(err)

// pobranie pliku z odpowiedzi: blob → link → klik → zwolnienie URL po pętli zdarzeń
// (natychmiastowe revoke potrafi anulować pobieranie w części przeglądarek)
export async function downloadBlob(response: Response, filename: string): Promise<void> {
  if (!response.ok) {
    // komunikat backendu (np. 409 „Agencja … nie ma adresu e-mail.”) zamiast samego kodu
    const body = await response.json().catch(() => ({}))
    throw new ApiError(response.status, detailMessage(body?.detail, `Błąd pobierania (${response.status})`))
  }
  saveBlob(await response.blob(), filename)
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

// komórka CSV: napis zaczynający się od = + - @ (tab/CR) dostaje apostrof — Excel nie
// wykona go jako formuły (jak backend quotes_core._csv_safe); liczby zostają liczbami
export function csvCell(v: unknown): string {
  let s = v == null ? '' : String(v)
  if (typeof v === 'string' && /^[=+\-@\t\r]/.test(s)) s = "'" + s
  return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export const toCsv = (rows: unknown[][], sep = ';'): string =>
  rows.map(r => r.map(csvCell).join(sep)).join('\n')

// CSV z BOM (polskie znaki w Excelu) → pobranie przez saveBlob
export function downloadCsv(filename: string, csv: string): void {
  saveBlob(new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' }), filename)
}

// pobranie chronionego pliku z ponowieniem po odświeżeniu sesji (401) — jak request();
// `form` = POST z plikami (np. raport Excel z wgranych PDF-ów), z nagłówkiem CSRF
export async function downloadFile(path: string, filename: string, form?: FormData): Promise<void> {
  if (form) assertUploadSize(form.values())
  const send = () => (form ? fetch(path, { method: 'POST', body: form, headers: CSRF_HEADERS }) : fetch(path))
  let response = await send()
  if (response.status === 401 && (await tryRefresh())) response = await send()
  await downloadBlob(response, filename)
}

// 2FA: przy włączonym TOTP backend zamiast cookies zwraca {totp_required, pending_token};
// LoginPage pokazuje wtedy drugi krok (kod z aplikacji → /api/auth/2fa/verify).
export interface LoginResult {
  totp_required?: boolean
  pending_token?: string
}

export async function login(username: string, password: string): Promise<LoginResult> {
  const form = new URLSearchParams({ username, password })
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { ...CSRF_HEADERS, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(response.status, detailMessage(body.detail, 'Błąd logowania'))
  }
  // tokeny trafiają do cookies HttpOnly — nic nie zapisujemy po stronie klienta
  return response.json().catch(() => ({})) as Promise<LoginResult>
}

export async function logoutRequest() {
  await fetch('/api/auth/logout', { method: 'POST', headers: CSRF_HEADERS }).catch(() => {})
}
