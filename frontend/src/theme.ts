// #62 — dark mode: jedno źródło prawdy dla motywu (localStorage 'theme').
// Zastosowane w main.tsx przed renderem (bez FOUC) i w ThemeToggle (przełącznik).
import { applyThemeColors } from './themeColors'

export type Theme = 'light' | 'dark'

export function getStoredTheme(): Theme {
  return localStorage.getItem('theme') === 'dark' ? 'dark' : 'light'
}

export function applyTheme(theme: Theme) {
  if (theme === 'dark') document.documentElement.setAttribute('data-theme', 'dark')
  else document.documentElement.removeAttribute('data-theme')
  applyThemeColors(theme)   // kolory z Administracji → Kolory dla tego motywu
}
