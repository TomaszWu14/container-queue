// @vitest-environment jsdom
// Wspólny znacznik trybu dowozu (kolejka / szuflada / karta / filtr / formularz).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { TRANSPORT_TYPES, TransportBadge, TransportPick } from './TransportBadge'

afterEach(cleanup)

// ślad ikony — każdy tryb ma własny rysunek (statek / samolot / wagon / ciężarówka / sam kontener)
const MARK: Record<string, string> = {
  morski: 'M2.5 13.5h19', lotniczy: 'M21 4.2c', kola: 'M15 8.5h3.6', kolej: 'M1.5 21.8h21', inne: 'M7 6v11',
}

describe('TransportBadge', () => {
  it.each([['morski', 'morski'], ['lotniczy', 'lotniczy'], ['kola', 'koła'], ['kolej', 'kolej'], ['inne', 'inne']] as const)(
    '%s → etykieta „%s”, aria/title, własna ikona 15px', (type, name) => {
      render(<TransportBadge type={type} />)
      const el = screen.getByRole('img', { name })
      expect(el.getAttribute('title')).toBe(name)
      expect(el.textContent).toBe(name)
      expect(el.className).toBe(`tr-badge tr-badge--${type}`)
      const svg = el.querySelector('svg')!
      expect(svg.getAttribute('aria-hidden')).toBe('true')
      expect(svg.getAttribute('width')).toBe('15')
      expect(svg.innerHTML).toContain(MARK[type])
      for (const other of TRANSPORT_TYPES.filter(o => o !== type)) expect(svg.innerHTML).not.toContain(MARK[other])
    })

  it.each([['drogowo', 'drogowo', 'M15 8.5h3.6'], ['intermodal', 'intermodal', 'M17.3 13.3']] as const)(
    'dowóz po odprawie %s → etykieta „%s” i własna ikona', (type, name, mark) => {
      render(<TransportBadge type={type} />)
      const el = screen.getByRole('img', { name })
      expect(el.className).toBe(`tr-badge tr-badge--${type}`)
      expect(el.querySelector('svg')!.innerHTML).toContain(mark)
    })

  it('size="md" (karty) — ikona 20px i modyfikator', () => {
    render(<TransportBadge type="kolej" size="md" />)
    const el = screen.getByRole('img', { name: 'kolej' })
    expect(el.classList.contains('tr-badge--md')).toBe(true)
    expect(el.querySelector('svg')!.getAttribute('width')).toBe('20')
  })
})

describe('TransportPick', () => {
  it('przycisk na tryb z pigułką; klik wybiera, klik w wybrany czyści', () => {
    const onChange = vi.fn()
    const { rerender } = render(<TransportPick label="Transport" value="" onChange={onChange} />)
    expect(screen.getByRole('group', { name: 'Transport' })).toBeTruthy()
    const btn = screen.getByRole('button', { name: 'kolej' })
    expect(btn.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(btn)
    expect(onChange).toHaveBeenLastCalledWith('kolej')
    rerender(<TransportPick label="Transport" value="kolej" onChange={onChange} />)
    expect(screen.getByRole('button', { name: 'kolej' }).getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: 'kolej' }))
    expect(onChange).toHaveBeenLastCalledWith('')
  })
})
