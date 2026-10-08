// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { HelpTip } from './HelpTip'
import { relTime } from './dates'
import { readAppCss } from './appCss.testutil'

afterEach(() => cleanup())

describe('HelpTip — popover', () => {
  it('otwiera się po kliknięciu i zamyka po Escape', () => {
    render(<HelpTip label="Pomoc" text="Treść pomocy" />)
    expect(screen.queryByText('Treść pomocy')).toBeNull()
    fireEvent.click(screen.getByLabelText('Pomoc'))
    expect(screen.getByText('Treść pomocy')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByText('Treść pomocy')).toBeNull()
  })

  it('zamyka się po kliknięciu poza popoverem', () => {
    render(<HelpTip label="Pomoc" text="Treść pomocy" />)
    fireEvent.click(screen.getByLabelText('Pomoc'))
    expect(screen.getByText('Treść pomocy')).toBeTruthy()
    fireEvent.click(window)
    expect(screen.queryByText('Treść pomocy')).toBeNull()
  })
})

describe('relTime — progi', () => {
  const now = new Date('2026-09-03T12:00:00Z').getTime()

  it('brak daty → nigdy/never/nunca', () => {
    expect(relTime(null, 'pl', now)).toBe('nigdy')
    expect(relTime(undefined, 'en', now)).toBe('never')
    expect(relTime(null, 'pt', now)).toBe('nunca')
  })

  it('poniżej minuty → przed chwilą', () => {
    expect(relTime(new Date(now - 30_000).toISOString(), 'pl', now)).toBe('przed chwilą')
  })

  it('minuty', () => {
    expect(relTime(new Date(now - 5 * 60_000).toISOString(), 'pl', now)).toBe('5 min temu')
  })

  it('godziny', () => {
    expect(relTime(new Date(now - 3 * 3600_000).toISOString(), 'pl', now)).toBe('3 godz. temu')
  })

  it('dni', () => {
    expect(relTime(new Date(now - 2 * 24 * 3600_000).toISOString(), 'pl', now)).toBe('2 dni temu')
  })
})

describe('helptip/tracking — strażnik CSS', () => {
  it('style aplikacji (src/styles) zawiera klasy .help-tip, .help-pop', () => {
    const css = readAppCss()
    expect(css).toContain('.help-tip')
    expect(css).toContain('.help-pop')
  })
})
