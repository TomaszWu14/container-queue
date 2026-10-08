// @vitest-environment jsdom
import type { ReactElement } from 'react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { LangContext } from './i18n'
import Onboarding from './Onboarding'
import ThemeToggle from './ThemeToggle'
import { applyTheme, getStoredTheme } from './theme'

afterEach(() => { cleanup(); localStorage.clear(); document.documentElement.removeAttribute('data-theme') })
beforeEach(() => localStorage.clear())

const withPl = (ui: ReactElement) => (
  <LangContext.Provider value={{ lang: 'pl', setLang: () => {} }}>{ui}</LangContext.Provider>
)

describe('Onboarding — #65', () => {
  it('pokazuje pierwszy krok gdy brak onboarded, Pomiń zamyka i zapisuje flagę', () => {
    render(withPl(<Onboarding />))
    expect(screen.getByText(/centrum systemu/)).toBeTruthy()
    fireEvent.click(screen.getByText('Pomiń'))
    expect(screen.queryByText(/centrum systemu/)).toBeNull()
    expect(localStorage.getItem('onboarded')).toBe('1')
  })

  it('nie renderuje się gdy onboarded już ustawione', () => {
    localStorage.setItem('onboarded', '1')
    render(withPl(<Onboarding />))
    expect(screen.queryByText(/centrum systemu/)).toBeNull()
  })

  // audyt UI Etap 4: na telefonie link „Kolejka” jest w zwiniętym menu (prostokąt 0×0) — dymek
  // wyśrodkowany, nie w rogu (10, 0); widoczna kotwica dalej ustawia dymek pod sobą
  it('schowana kotwica (0×0) → dymek wyśrodkowany; widoczna → pod kotwicą', () => {
    const a = document.createElement('a')
    a.setAttribute('data-tour', 'kolejka')
    document.body.appendChild(a)
    const { container, unmount } = render(withPl(<Onboarding />))
    expect(container.querySelector('.ob-overlay')!.classList.contains('ob-center')).toBe(true)
    unmount()
    a.getBoundingClientRect = () => ({ top: 10, left: 40, bottom: 40, right: 140, width: 100, height: 30, x: 40, y: 10, toJSON: () => ({}) })
    const second = render(withPl(<Onboarding />))
    expect(second.container.querySelector('.ob-overlay')!.classList.contains('ob-center')).toBe(false)
    expect((second.container.querySelector('.ob-bubble') as HTMLElement).style.top).toBe('50px')
    a.remove()
  })

  it('Dalej przechodzi przez kolejne kroki aż do końca', () => {
    render(withPl(<Onboarding />))
    for (let i = 0; i < 4; i++) fireEvent.click(screen.getByText('Dalej'))
    expect(screen.getByText(/Śledzenie/)).toBeTruthy()
    fireEvent.click(screen.getByText('Dalej'))
    expect(localStorage.getItem('onboarded')).toBe('1')
  })
})

describe('theme — #62', () => {
  it('getStoredTheme domyślnie light, applyTheme ustawia data-theme na html', () => {
    expect(getStoredTheme()).toBe('light')
    applyTheme('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    applyTheme('light')
    expect(document.documentElement.getAttribute('data-theme')).toBeNull()
  })

  it('ThemeToggle przełącza i zapisuje localStorage', () => {
    render(withPl(<ThemeToggle />))
    const btn = screen.getByRole('button')
    fireEvent.click(btn)
    expect(localStorage.getItem('theme')).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    fireEvent.click(btn)
    expect(localStorage.getItem('theme')).toBe('light')
  })
})
