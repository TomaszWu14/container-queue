// @vitest-environment jsdom
// Kolory motywów: warstwa osobista wygrywa z firmową, zmiana motywu podmienia zestaw, śmieci
// (zły token / nie-hex, np. próba wstrzyknięcia CSS) nigdy nie trafiają do style.setProperty.
import { afterEach, describe, expect, it } from 'vitest'
import { applyTheme } from './theme'
import { USER_KEY, sanitize, setThemeColors } from './themeColors'

const prop = (t: string) => document.documentElement.style.getPropertyValue(t)

afterEach(() => { localStorage.clear(); setThemeColors({ light: {}, dark: {} }); applyTheme('light') })

describe('themeColors', () => {
  it('sanitize odrzuca złe tokeny i wartości', () => {
    expect(sanitize({ light: { '--bg': '#0e1f3f', color: '#000000', '--x': 'red; background:url(x)' }, dark: 5 }))
      .toEqual({ light: { '--bg': '#0e1f3f' }, dark: {} })
    expect(sanitize(null)).toEqual({ light: {}, dark: {} })
  })

  it('firmowe per motyw, osobiste na wierzchu; przełączenie motywu zdejmuje poprzedni zestaw', () => {
    localStorage.setItem(USER_KEY, JSON.stringify({ light: { '--bg': '#111111' }, dark: {} }))
    setThemeColors({ light: { '--bg': '#eeeeee', '--panel': '#ffffff' }, dark: { '--kq-row-dlt': '#4d3a12' } })
    expect(prop('--bg')).toBe('#111111')              // osobisty wygrywa
    expect(prop('--panel')).toBe('#ffffff')           // firmowy
    applyTheme('dark')
    expect(prop('--bg')).toBe('')                     // jasny zestaw zdjęty
    expect(prop('--kq-row-dlt')).toBe('#4d3a12')
  })
})
