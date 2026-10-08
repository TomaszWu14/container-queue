// Tylko dla testów: rozwiązuje tokeny CSS tak jak przeglądarka — 00-tokens.css + 01-tokens-base.css,
// aliasy var(--x[, fallback]) i color-mix(in srgb, A p%, B). Wynik: nazwa → hex (#rrggbb).
import { readFileSync } from 'node:fs'

const read = (f: string) => readFileSync(new URL(`./${f}`, import.meta.url), 'utf-8')
export const CSS = { tokens: read('00-tokens.css'), base: read('01-tokens-base.css') }

type Raw = Record<string, string>

// selektor może otwierać listę, np. ":root[data-theme='dark'], .theme-dark {"
function blocks(css: string, selector: string): Raw {
  const out: Raw = {}
  const esc = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  for (const m of css.matchAll(new RegExp(`(^|[},\\s])${esc}(?:\\s*,[^{]*)?\\s*\\{([^}]*)\\}`, 'g'))) {
    for (const d of m[2].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[d[1]] = d[2].trim()
  }
  return out
}

const hex2 = (n: number) => Math.round(n).toString(16).padStart(2, '0')
const rgb = (h: string) => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16))

function resolve(v: string, map: Raw, depth = 0): string | null {
  if (depth > 12) return null
  v = v.trim()
  if (/^#[0-9a-fA-F]{6}$/.test(v)) return v.toLowerCase()
  const ref = v.match(/^var\(\s*(--[\w-]+)\s*(?:,\s*(.+))?\)$/)
  if (ref) return map[ref[1]] !== undefined ? resolve(map[ref[1]], map, depth + 1)
    : ref[2] !== undefined ? resolve(ref[2], map, depth + 1) : null
  const mix = v.match(/^color-mix\(in srgb,\s*(.+?)\s+(\d+(?:\.\d+)?)%,\s*(.+)\)$/)
  if (mix) {
    const a = resolve(mix[1], map, depth + 1), b = resolve(mix[3], map, depth + 1)
    if (!a || !b) return null
    const p = Number(mix[2]) / 100
    const [ca, cb] = [rgb(a), rgb(b)]
    return '#' + ca.map((c, i) => hex2(c * p + cb[i] * (1 - p))).join('')
  }
  return null
}

function resolved(raw: Raw): Record<string, string> {
  const out: Record<string, string> = {}
  for (const k of Object.keys(raw)) { const r = resolve(raw[k], raw); if (r) out[k] = r }
  return out
}

const DARK = ":root[data-theme='dark']"
const lightRaw = (): Raw => ({ ...blocks(CSS.tokens, ':root'), ...blocks(CSS.base, ':root') })
const darkRaw = (): Raw => ({ ...lightRaw(), ...blocks(CSS.tokens, DARK), ...blocks(CSS.base, DARK) })

/** Rozwiązane tokeny motywu. */
export function tokens(theme: 'light' | 'dark'): Record<string, string> {
  return resolved(theme === 'light' ? lightRaw() : darkRaw())
}
