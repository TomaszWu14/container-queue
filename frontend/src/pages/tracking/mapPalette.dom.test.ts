// @vitest-environment jsdom
// Kolory mapy z tokenów ciemnego motywu (scope .theme-dark w 00-tokens.css) — audyt UI S6.
import { afterEach, describe, expect, it } from 'vitest'
import { COMPANY_FILL, readMapPalette } from './trackingModel'

afterEach(() => { document.head.innerHTML = '' })

describe('readMapPalette', () => {
  it('czyta ciemne warianty tokenów niezależnie od motywu strony', () => {
    const style = document.createElement('style')
    style.textContent = `:root { --st-W_DOSTAWIE-ink: rgb(1,1,1); }
      .theme-dark { --st-W_DOSTAWIE-ink: rgb(245,176,122); --co-acme: rgb(122,167,255); --bg: rgb(15,23,32); }`
    document.head.appendChild(style)
    const p = readMapPalette()
    expect(p.status.W_DOSTAWIE).toBe('rgb(245,176,122)')
    expect(p.company.ACME).toBe('rgb(122,167,255)')
    expect(p.ink).toBe('rgb(15,23,32)')
    // brak tokenu = brak wpisu (wywołujący ma własny fallback), a sonda nie zostaje w DOM
    expect(p.status.ZAPOWIEDZIANY).toBeUndefined()
    expect(document.querySelector('.theme-dark')).toBeNull()
  })

  it('karta statku: wypełnienie spółki z tokenu -fill (ten sam w obu motywach)', () => {
    expect(COMPANY_FILL.COBALT).toBe('var(--co-cobalt-fill)')
    expect(COMPANY_FILL.TRANZYT).toBe('var(--co-tranzyt-fill)')
  })
})
