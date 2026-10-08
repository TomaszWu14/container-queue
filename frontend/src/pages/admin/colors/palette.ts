// Administracja → Kolory: które tokeny wolno zmienić (grupy), ich kolory domyślne (z arkuszy CSS)
// i paleta 500 barw do wyboru. Bez hexów w kodzie — domyślne czytamy z 00-tokens.css, paletę liczymy.
import tokensCss from '../../../styles/00-tokens.css?raw'
import queueCss from '../../../styles/11-kolejka-enterprise.css?raw'
import type { Mode } from '../../../themeColors'

export interface TokenDef { token: string; label: string }
export interface Group { key: string; label: string; tokens: TokenDef[] }

// label = klucz i18n (i18n/features/kolory.ts); kolejność = kolejność na ekranie
export const GROUPS: Group[] = [
  { key: 'base', label: 'colGrpBase', tokens: [
    { token: '--bg', label: 'colTokBg' }, { token: '--panel', label: 'colTokPanel' },
    { token: '--surface-2', label: 'colTokSurface' }, { token: '--border', label: 'colTokBorder' }] },
  { key: 'text', label: 'colGrpText', tokens: [
    { token: '--text', label: 'colTokText' }, { token: '--text-muted', label: 'colTokMuted' }] },
  { key: 'accent', label: 'colGrpAccent', tokens: [
    { token: '--accent', label: 'colTokAccent' }, { token: '--accent-ink', label: 'colTokAccentInk' },
    { token: '--chrome', label: 'colTokChrome' }, { token: '--chrome-text', label: 'colTokChromeText' }] },
  { key: 'dlt', label: 'colGrpDlt', tokens: [
    { token: '--kq-row-dlt', label: 'colTokRow' }, { token: '--kq-row-dlt-hover', label: 'colTokRowHover' },
    { token: '--wh-dlt-bar', label: 'colTokBar' }, { token: '--wh-dlt-ink', label: 'colTokInk' }] },
  { key: 'acme', label: 'colGrpAcme', tokens: [
    { token: '--kq-row-acme', label: 'colTokRow' }, { token: '--kq-row-acme-hover', label: 'colTokRowHover' },
    { token: '--wh-acme-bar', label: 'colTokBar' }, { token: '--wh-acme-ink', label: 'colTokInk' }] },
  { key: 'none', label: 'colGrpNone', tokens: [
    { token: '--kq-row-none', label: 'colTokRow' }, { token: '--wh-none-bar', label: 'colTokBar' }] },
]
export const TOKENS = GROUPS.flatMap(g => g.tokens.map(t => t.token))

type Raw = Record<string, string>
function block(css: string, selector: RegExp): Raw {
  const out: Raw = {}
  for (const m of css.matchAll(selector)) {
    for (const d of m[1].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[d[1]] = d[2].trim()
  }
  return out
}
const LIGHT = /:root\s*\{([^}]*)\}/g                    // bez [data-theme] — sam :root
const DARK = /:root\[data-theme='dark'\][^{]*\{([^}]*)\}/g

function resolve(v: string | undefined, map: Raw, depth = 0): string | null {
  if (!v || depth > 8) return null
  if (/^#[0-9a-fA-F]{6}$/.test(v)) return v.toLowerCase()
  const ref = v.match(/^var\(\s*(--[\w-]+)\s*(?:,\s*(.+))?\)$/)
  return ref ? resolve(map[ref[1]] ?? ref[2], map, depth + 1) : null
}

// kolory domyślne motywu = arkusze aplikacji; wiersz bez magazynu domyślnie = panel
export function defaults(mode: Mode): Record<string, string> {
  const light = { ...block(tokensCss, LIGHT), ...block(queueCss, LIGHT) }
  const map = mode === 'light' ? light : { ...light, ...block(tokensCss, DARK), ...block(queueCss, DARK) }
  map['--kq-row-none'] ??= 'var(--panel)'
  return Object.fromEntries(TOKENS.map(t => [t, resolve(map[t], map) ?? hsl(0, 0, 0.5)]))
}

const hex2 = (n: number) => Math.round(Math.max(0, Math.min(255, n))).toString(16).padStart(2, '0')
export function hsl(h: number, s: number, l: number): string {
  const a = s * Math.min(l, 1 - l)
  const f = (n: number) => { const k = (n + h / 30) % 12; return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)) }
  return '#' + [f(0), f(8), f(4)].map(x => hex2(x * 255)).join('')
}

// 20 kolumn (19 odcieni co ~19° + szarości lekko granatowe) × 25 jasności = 500 barw; ciemne i jasne
// końce skali są gęstsze, bo tam siedzą tła motywów (ciemny ~5–20%, jasny ~88–97%)
export const LIGHTNESS = Array.from({ length: 25 }, (_, i) =>
  0.04 + 0.93 * (0.5 - 0.5 * Math.cos(Math.PI * i / 24)))   // rozstaw cosinusowy: gęściej na końcach
export const HUES = Array.from({ length: 19 }, (_, i) => Math.round(i * 360 / 19))
export function palette(): string[][] {
  return LIGHTNESS.map(l => [...HUES.map(h => hsl(h, l < 0.2 || l > 0.9 ? 0.45 : 0.62, l)), hsl(215, 0.18, l)])
}

const lum = (hex: string) => {
  const v = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(x => x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4)
  return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
}
export function contrast(a: string, b: string): number {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}

// pary „tekst na tle” sprawdzane na żywo (WCAG AA: 4,5 tekst, 3 elementy graficzne)
export const CHECKS: { fg: string; bg: string; label: string; min: number }[] = [
  { fg: '--text', bg: '--panel', label: 'colChkTextPanel', min: 4.5 },
  { fg: '--text-muted', bg: '--panel', label: 'colChkMutedPanel', min: 4.5 },
  { fg: '--text', bg: '--kq-row-dlt', label: 'colChkTextDlt', min: 4.5 },
  { fg: '--text', bg: '--kq-row-acme', label: 'colChkTextAcme', min: 4.5 },
  { fg: '--text', bg: '--kq-row-none', label: 'colChkTextNone', min: 4.5 },
  { fg: '--chrome-text', bg: '--chrome', label: 'colChkChrome', min: 4.5 },
  { fg: '--wh-dlt-bar', bg: '--kq-row-dlt', label: 'colChkBarDlt', min: 3 },
  { fg: '--wh-acme-bar', bg: '--kq-row-acme', label: 'colChkBarAcme', min: 3 },
]
