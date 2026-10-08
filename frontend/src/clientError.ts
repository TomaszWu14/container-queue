// Beacon błędów frontendu → POST /api/client-error (bez auth, backend zwraca 202).
// Bez Sentry: fetch z keepalive, przycięcie pól do limitów backendu, dedupe kolejnych
// identycznych komunikatów i twardy limit ~10 zgłoszeń na sesję (pętla błędów nie
// może zDDoS-ować własnego backendu).

import { CSRF_HEADERS } from './csrf'

const LIMITS = { name: 200, message: 2000, stack: 8000, url: 500 }
const MAX_PER_SESSION = 10

let sent = 0
let lastMessage = ''

export function sendClientError(name: string, message: string, stack?: string): void {
  const msg = (message || '').slice(0, LIMITS.message)
  if (sent >= MAX_PER_SESSION || msg === lastMessage) return
  sent++
  lastMessage = msg
  const body = JSON.stringify({
    name: (name || 'Error').slice(0, LIMITS.name),
    message: msg,
    stack: (stack || '').slice(0, LIMITS.stack),
    url: window.location.href.slice(0, LIMITS.url),
  })
  try {
    fetch('/api/client-error', {
      method: 'POST',
      headers: { ...CSRF_HEADERS, 'Content-Type': 'application/json' },
      body,
      keepalive: true,
    }).catch(() => {})
  } catch { /* beacon nigdy nie może sam rzucić */ }
}

export function installErrorBeacon(): void {
  window.onerror = (message, _src, _line, _col, error) => {
    sendClientError(error?.name ?? 'Error', String(error?.message ?? message), error?.stack)
  }
  window.addEventListener('unhandledrejection', event => {
    const reason: unknown = event.reason
    const err = reason instanceof Error ? reason : null
    sendClientError(err?.name ?? 'UnhandledRejection',
      err?.message ?? String(reason), err?.stack)
  })
}
