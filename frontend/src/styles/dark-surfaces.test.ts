// Strażnik tła powierzchni w trybie ciemnym (audyt UI S7/S14 — UX-010, UX-009): wybrane powierzchnie
// (wyceny, kalendarz, szuflada i zakładki kolejki, zamówienia, alerty) biorą tło z tokena, więc w dark
// mode są ciemne — jasne hexy (#eef4ff, #f1f4f8, #fdf3f2…) świeciły na granatowym tle.
import { describe, expect, it } from 'vitest'
import { readAppCss } from '../appCss.testutil'
import { tokens } from './tokenMap'

const SURFACES = [
  '.quote-item.active', '.quote-winner td', '.panel.attention', 'td.over-limit', '.bar-track',
  '.cal-year-step', '.cal-bar', '.kq-bubble', '.kq-doc-ico', '.kq-doc-ico.pdf', '.kq-dr-stages i',
  '.lock-btn.unlocked', '.invoice-review input.invalid',
]

function lum(hex: string): number {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

// tło z ostatniej reguły dokładnie dla selektora (kaskada: późniejsza wygrywa)
function background(css: string, sel: string): string | undefined {
  const esc = sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const hits = [...css.matchAll(new RegExp(`(?:^|[}\\n,])\\s*${esc}\\s*\\{([^}]*)\\}`, 'g'))]
    .map(m => m[1].match(/(?:^|;)\s*background(?:-color)?\s*:\s*([^;]+)/)?.[1].trim()).filter(Boolean)
  return hits[hits.length - 1]
}

describe('powierzchnie w trybie ciemnym', () => {
  const css = readAppCss().replace(/\/\*[\s\S]*?\*\//g, '')
  const dark = tokens('dark')

  it.each(SURFACES)('%s: tło z tokena, ciemne w dark', sel => {
    const bg = background(css, sel)
    expect(bg, `${sel} bez tła`).toBeTruthy()
    const ref = bg!.match(/^var\(\s*(--[\w-]+)\s*\)$/)
    expect(ref, `${sel}: ${bg} — użyj tokena`).not.toBeNull()
    const hex = dark[ref![1]]
    expect(hex, `${ref![1]} bez wartości w dark`).toMatch(/^#[0-9a-f]{6}$/)
    expect(lum(hex)).toBeLessThan(0.08)
  })
})
