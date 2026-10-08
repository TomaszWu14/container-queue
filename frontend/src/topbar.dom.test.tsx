// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

vi.mock('./api', () => ({
  api: { get: () => Promise.resolve({}), post: () => Promise.resolve({}), patch: () => Promise.resolve({}) },
}))
vi.mock('./NotificationsBell', () => ({ default: () => null }))

import Sidebar from './Sidebar'
import { UserContext } from './userContext'
import type { User } from './types'

afterEach(cleanup)

function renderBar(user: Partial<User>) {
  render(
    <UserContext.Provider value={{ user: { id: 1, login: 'u', full_name: 'U', ...user } as User, reload: () => {} }}>
      <MemoryRouter initialEntries={['/pulpit']}><Sidebar onLogout={() => {}} /></MemoryRouter>
    </UserContext.Provider>,
  )
}

describe('Górny pasek 48 px', () => {
  it('„Analiza rozładunków" jest PIERWSZĄ pozycją menu Analiza i prowadzi do zakładki analysis kolejki', () => {
    renderBar({ role: 'admin' })
    fireEvent.click(screen.getByRole('button', { name: /Analiza/ }))
    const links = document.querySelectorAll('.tn-group.open .tn-drop-link')
    expect(links[0].textContent).toBe('Analiza rozładunków')
    expect(links[0].getAttribute('href')).toBe('/kolejka?spolka=analysis')
  })

  it('konto bez wglądu we wszystkie spółki nie widzi „Analizy rozładunków"', () => {
    renderBar({ role: 'logistics', view_all_companies: false })
    fireEvent.click(screen.getByRole('button', { name: /Analiza/ }))
    expect(document.querySelector('.tn-group.open')?.textContent).not.toContain('Analiza rozładunków')
  })

  it('tryb ikon: każda pozycja nav ma title/aria-label i etykietę .tn-label chowaną < 1440 px (poza aktywną)', () => {
    renderBar({ role: 'admin' })
    const navLinks = document.querySelectorAll('.tn-menu .tn-link')
    expect(navLinks.length).toBeGreaterThan(3)
    navLinks.forEach(a => {
      const label = a.querySelector('.tn-label')?.textContent
      expect(label).toBeTruthy()
      expect(a.getAttribute('title')).toBe(label)
      expect(a.getAttribute('aria-label')).toBe(label)
    })
    const css = readFileSync(join(__dirname, 'styles', '09-modules-rail-header.css'), 'utf-8')
    expect(css).toMatch(/@media \(max-width: 1439px\) \{\s*\.tn-link:not\(\.active\) \.tn-label \{ display: none; \}/)
  })

  it('zegar w jednej linii: RAD · SHA · POR w formacie gg:mm', () => {
    renderBar({ role: 'admin' })
    const txt = document.querySelector('.worldclock')?.textContent ?? ''
    expect(txt).toMatch(/^RAD \d\d:\d\d·SHA \d\d:\d\d·POR \d\d:\d\d$/)
  })
})
