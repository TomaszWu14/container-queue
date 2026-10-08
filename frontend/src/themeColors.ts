// Kolory motywów w dwóch warstwach: firmowe (admin, Administracja → Kolory, wspólne dla wszystkich)
// i osobiste (każdy użytkownik, menu → Moje kolory; profil konta przez prefs.ts) — osobiste wygrywają.
// Nadpisania tokenów CSS dla motywu jasnego i ciemnego. Styl inline na <html> wygrywa z :root i
// :root[data-theme='dark'] z arkuszy, więc wystarczy podmienić zestaw przy zmianie motywu.
// Kopia w localStorage — kolory od pierwszej klatki, zanim przyjdzie odpowiedź API (bez mignięcia).
export type Mode = 'light' | 'dark'
export type ThemeColors = Record<Mode, Record<string, string>>

const KEY = 'themeColors'
export const USER_KEY = 'userThemeColors'   // synchronizowany z kontem (prefs.ts SYNC_KEYS)
const TOKEN = /^--[a-z0-9][a-z0-9-]{1,40}$/
const HEX = /^#[0-9a-f]{6}$/

export const EMPTY: ThemeColors = { light: {}, dark: {} }

// nie ufamy kształtowi (localStorage, mock API) — złe wpisy odrzucamy, nigdy nie trafiają do CSS
export function sanitize(raw: unknown): ThemeColors {
  const out: ThemeColors = { light: {}, dark: {} }
  if (!raw || typeof raw !== 'object') return out
  for (const mode of ['light', 'dark'] as const) {
    const map = (raw as Record<string, unknown>)[mode]
    if (!map || typeof map !== 'object') continue
    for (const [token, color] of Object.entries(map as Record<string, unknown>)) {
      if (TOKEN.test(token) && typeof color === 'string' && HEX.test(color)) out[mode][token] = color
    }
  }
  return out
}

let current: ThemeColors = EMPTY
let applied: string[] = []

function read(key: string): ThemeColors {
  try { return sanitize(JSON.parse(localStorage.getItem(key) ?? 'null')) } catch { return EMPTY }
}

export function companyColors(): ThemeColors {
  if (current === EMPTY) current = read(KEY)
  return current
}
export const userColors = (): ThemeColors => read(USER_KEY)

const activeMode = (): Mode =>
  document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'

// wołane z theme.applyTheme przy każdej zmianie motywu (i na starcie, z kopii w localStorage)
export function applyThemeColors(mode: Mode = activeMode()) {
  const colors = { ...companyColors()[mode], ...userColors()[mode] }
  const style = document.documentElement.style
  for (const token of applied) style.removeProperty(token)
  applied = Object.keys(colors)
  for (const token of applied) style.setProperty(token, colors[token])
}

export function setThemeColors(colors: ThemeColors) {
  current = sanitize(colors)
  try { localStorage.setItem(KEY, JSON.stringify(current)) } catch { /* prywatne okno — tylko ta sesja */ }
  applyThemeColors()
}
