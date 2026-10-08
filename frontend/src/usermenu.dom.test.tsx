// @vitest-environment jsdom
// Menu użytkownika (audyt UI C25 — UX-043): nagłówek z imieniem i rolą (pod 1600 px przycisk pokazuje
// sam awatar), pozycje z ikoną i tekstem — motyw z podpisem zamiast samego księżyca, język z etykietą,
// przełącznik powiadomień nazwany jako preferencja powiadomień (to nie filtr danych kolejki).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('./api', () => ({
  api: { get: () => Promise.resolve({}), post: () => Promise.resolve({}), patch: () => Promise.resolve({}) },
}))
vi.mock('./NotificationsBell', () => ({ default: () => null }))

import Sidebar from './Sidebar'
import { UserContext } from './userContext'
import type { User } from './types'

afterEach(() => { cleanup(); document.documentElement.removeAttribute('data-theme'); localStorage.clear() })

function openMenu() {
  render(
    <UserContext.Provider value={{ user: { id: 1, login: 'jkowal', full_name: 'Jan Kowalski', role: 'logistics' } as User, reload: () => {} }}>
      <MemoryRouter initialEntries={['/pulpit']}><Sidebar onLogout={() => {}} /></MemoryRouter>
    </UserContext.Provider>,
  )
  fireEvent.click(document.querySelector('.tn-user')!)
  return document.querySelector('.tn-usermenu.open .tn-drop') as HTMLElement
}

describe('menu użytkownika', () => {
  it('nagłówek: imię i rola', () => {
    const drop = openMenu()
    const head = drop.querySelector('.tn-drop-head')!
    expect(head.textContent).toContain('Jan Kowalski')
    expect(head.textContent).toContain('Logistyka')
  })

  it('pozycje z ikoną i tekstem; motyw i język podpisane', () => {
    const drop = openMenu()
    const security = screen.getByRole('link', { name: 'Bezpieczeństwo konta' })
    expect(security.querySelector('svg')).not.toBeNull()
    const theme = drop.querySelector('.tn-theme-toggle')!
    expect(theme.textContent).toMatch(/Motyw: (jasny|ciemny)/)
    fireEvent.click(theme)
    expect(drop.querySelector('.tn-theme-toggle')!.textContent).toBe('Motyw: ciemny')
    expect(screen.getByLabelText('Język').closest('label')?.textContent).toContain('Język')
    // preferencja powiadomień, nie filtr danych
    expect(screen.getByRole('checkbox', { name: 'Powiadomienia tylko o obserwowanych' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Wyloguj' }).querySelector('svg')).not.toBeNull()
  })
})
