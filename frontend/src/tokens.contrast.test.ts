// Strażnik WCAG AA (4.5:1) dla tokenów tekstu na tokenach tła — wyblakłe szare napisy
// (etykiety, nieaktywne liczniki, nagłówki kolumn) naprawiamy w tokenach, nie per miejsce.
import { describe, expect, it } from 'vitest'
import { CSS, tokens } from './styles/tokenMap'
import { readAppCss } from './appCss.testutil'

// wartości rozwiązane jak w przeglądarce: 00-tokens.css (design system) + aliasy z 01-tokens-base.css
const css = CSS.base

function lum(hex: string): number {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
export function contrast(a: string, b: string): number {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const light = tokens('light')
const dark = tokens('dark')
const TEXT = ['--text', '--muted', '--muted-strong', '--accent-ink']

function pairs(tokens: Record<string, string>, bgs: string[]) {
  return TEXT.flatMap(fg => bgs.filter(bg => tokens[bg]).map(bg =>
    [`${fg} na ${bg}`, contrast(tokens[fg], tokens[bg])] as const))
}

describe('kontrast tokenów (WCAG AA 4.5:1)', () => {
  it('liczy znane wartości (czarny/biały = 21:1)', () => {
    expect(contrast('#000000', '#ffffff')).toBeCloseTo(21, 5)
  })

  it('jasny motyw: tekst/muted/nagłówki/akcent na wszystkich tłach', () => {
    const bad = pairs(light, ['--bg', '--panel', '--soft', '--banner-bg', '--accent-soft',
      '--wh-dlt-bg', '--wh-acme-bg', '--row-none']).filter(([, r]) => r < 4.5)
    expect(bad).toEqual([])
  })

  it('ciemny motyw: tekst/muted/nagłówki na tłach konsoli', () => {
    const bad = pairs(dark, ['--bg', '--panel', '--soft', '--banner-bg'])
      .filter(([k, r]) => r < 4.5 && !k.startsWith('--accent-ink na --accent-soft'))
    expect(bad).toEqual([])
  })

  it('znacznik trybu dowozu (--tr-*): tekst na swoim półprzezroczystym tle nałożonym na panel/tło', () => {
    // tło pigułki to rgba — liczymy kolor po nałożeniu na --panel i --bg
    const rgba = (theme: string, name: string) => {
      const start = css.indexOf(`${theme} {`)
      const body = css.slice(start, css.indexOf('}', start))
      const m = body.match(new RegExp(`${name}:\\s*rgba\\(([^)]+)\\)`))!
      return m[1].split(',').map(Number)
    }
    const over = ([r, g, b, a]: number[], hex: string) => '#' + [r, g, b].map((c, i) => {
      const base = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16)
      return Math.round(c * a + base * (1 - a)).toString(16).padStart(2, '0')
    }).join('')
    const bad: string[] = []
    for (const [theme, tokens] of [[':root', light], [":root[data-theme='dark']", dark]] as const) {
      for (const k of ['road', 'rail', 'other']) {
        for (const bg of ['--panel', '--bg']) {
          const r = contrast(tokens[`--tr-${k}`], over(rgba(theme, `--tr-${k}-bg`), tokens[bg]))
          if (r < 4.5) bad.push(`${theme} --tr-${k} na ${bg}: ${r.toFixed(2)}`)
        }
      }
    }
    expect(bad).toEqual([])
  })

  // jeden akcent w całej aplikacji (decyzja 2026-09-28): spółkę pokazuje kropka na zakładce
  // (--co-*), a nie przemalowany akcent — --accent* ustawiają tylko bloki motywu
  it('akcent jest jeden: poza blokami motywu żadna reguła nie nadpisuje --accent*', () => {
    const THEME = /^:root(\[data-theme='dark'\](, \.theme-dark)?)?$/
    const rules = readAppCss().replace(/\/\*[\s\S]*?\*\//g, '').match(/[^{}]+\{[^}]*\}/g) ?? []
    const bad = rules.filter(r => /--accent[\w-]*\s*:/.test(r.slice(r.indexOf('{'))))
      .map(r => r.slice(0, r.indexOf('{')).trim()).filter(sel => !THEME.test(sel))
    expect(bad).toEqual([])
  })
})

// audyt UI (Etap 4): --danger to alias --danger-ink — kolor TEKSTU, w ciemnym motywie jasny.
// Jako tło pod białym napisem dawał 2.3:1 („P1” na pulpicie). Tło z tekstem = --danger-fill.
describe('tło pod tekstem na kolorze błędu', () => {
  it('--danger-fill pod --text-on-fill ≥ 4.5:1 w obu motywach', () => {
    for (const tk of [light, dark]) expect(contrast(tk['--text-on-fill'], tk['--danger-fill'])).toBeGreaterThanOrEqual(4.5)
  })
  it('tło var(--danger) tylko dla elementów bez tekstu (kropki, paski)', () => {
    const NO_TEXT = /\.(age-dot|stage-track|kq-late-dot)/
    const rules = readAppCss().match(/[^{}]+\{[^}]*\}/g) ?? []
    const bad = rules.filter(r => /background(-color)?:\s*var\(--danger\)/.test(r))
      .map(r => r.slice(0, r.indexOf('{')).trim()).filter(sel => !NO_TEXT.test(sel))
    expect(bad).toEqual([])
  })
})
