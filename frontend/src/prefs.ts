// Profil widoku per user — mostek localStorage ↔ /api/auth/me/prefs.
// Ustawienia widoku kolejki (ukryte kolumny, gęstość wierszy, zapisane widoki,
// zwinięte pasma planowania) podążają za kontem między przeglądarkami:
// po zalogowaniu pullPrefs() zasiewa localStorage z serwera, a każdy zapis
// przez setPref() trafia lokalnie od razu i na serwer z debouncem.
import { api } from './api'

const SYNC_KEYS = ['queueViews', 'queueRowHeight', 'queueCollapsedPlanning', 'userThemeColors', 'kqColOrder']
const SYNC_PREFIX = 'timporye_cols_wide_'

const syncable = (k: string) => SYNC_KEYS.includes(k) || k.startsWith(SYNC_PREFIX)

/** Zasiew localStorage profilem z serwera — wołane raz po ustaleniu usera. */
export async function pullPrefs(): Promise<void> {
  try {
    const data = await api.get<Record<string, unknown>>('/api/auth/me/prefs')
    if (!data || typeof data !== 'object') return
    // Izolacja per user: usuń zastane klucze poprzedniego usera ZANIM zasiejemy —
    // inaczej na wspólnym komputerze user B widzi widoki A, a jego pierwszy zapis
    // (push wysyła cały syncowalny localStorage) wgrywa resztki A do profilu B.
    for (const k of [...Array(localStorage.length).keys()]
        .map(i => localStorage.key(i)!).filter(syncable)) {
      localStorage.removeItem(k)
    }
    for (const [k, v] of Object.entries(data)) {
      if (syncable(k) && typeof v === 'string') {
        try { localStorage.setItem(k, v) } catch { /* quota */ }
      }
    }
  } catch { /* offline/błąd → zostają ustawienia lokalne */ }
}

let timer: ReturnType<typeof setTimeout> | undefined

function push(): void {
  const out: Record<string, string> = {}
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i)
    if (k && syncable(k)) out[k] = localStorage.getItem(k) ?? ''
  }
  api.put('/api/auth/me/prefs', out).catch(() => { /* best-effort */ })
}

/** Anuluj odłożony zapis na serwer (testy: timer nie może przeżyć testu, który go zlecił). */
export function cancelPendingPrefs(): void { clearTimeout(timer); timer = undefined }

/** Zapis preferencji widoku: lokalnie natychmiast, na serwer z debouncem 1,2 s. */
export function setPref(key: string, value: string): void {
  try { localStorage.setItem(key, value) } catch { /* quota */ }
  clearTimeout(timer)
  timer = setTimeout(push, 1200)
}
