// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Rola sterowana z testu: mock /api/auth/me czyta ją przy każdym renderze.
let role = 'admin'
const user = () => ({ id: 1, login: 'u', role, full_name: 'U',
  must_change_password: false, view_all_companies: role === 'admin' })

vi.mock('./api', () => ({
  api: { get: (path: string) => Promise.resolve(path.includes('/auth/me') ? user() : []) },
  logoutRequest: () => Promise.resolve(),
  ApiError: class extends Error {},
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./pages/DashboardPage', () => ({ default: () => <div>DASHBOARD</div> }))

afterEach(cleanup)

import App from './App'

function mount() {
  return render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>)
}

describe('Górny pasek — sekcje wg roli', () => {
  it('admin widzi wszystkie sekcje, Administrację i linki w rozwijankach', async () => {
    role = 'admin'
    mount()
    // sekcje (przyciski rozwijane) — etykiety literalne
    await waitFor(() => expect(screen.getByRole('button', { name: /Operacje/ })).toBeTruthy(),
      { timeout: 5000 })
    expect(screen.getByRole('button', { name: /Analiza/ })).toBeTruthy()
    // najczęstsze ekrany to GŁÓWNE linki, nie pozycje w rozwijance
    expect(screen.queryByRole('button', { name: /Logistyka/ })).toBeNull()
    expect(document.querySelector('.tn-menu > a[href="/sledzenie"]')).not.toBeNull()
    expect(document.querySelector('.tn-menu > a[href="/spedycja"]')).not.toBeNull()
    // linki w rozwijankach są w DOM (ukryte tylko CSS-em); sprawdzamy po href
    const hrefs = Array.from(document.querySelectorAll('a')).map(a => a.getAttribute('href'))
    expect(hrefs).toContain('/administracja')      // tylko admin
    expect(hrefs).toContain('/analityka')          // sekcja Analiza
    expect(hrefs).toContain('/spedycja')           // link główny
    expect(hrefs).toContain('/profil')             // menu użytkownika
    expect(hrefs).toContain('/zamowienia')         // sekcja Operacje
  })

  it('rozwijanka otwiera się klikiem i tylko jedna naraz (nie hover)', async () => {
    role = 'admin'
    mount()
    const ops = await screen.findByRole('button', { name: /Operacje/ }, { timeout: 5000 })
    // aplikacja musi się ustabilizować (przekierowanie '/' → pulpit, dociągnięte dane) —
    // późny re-render po kliknięciu zamykał menu i test bywał niestabilny pod obciążeniem
    await screen.findByText('DASHBOARD', undefined, { timeout: 5000 })
    const log = screen.getByRole('button', { name: /Analiza/ })
    const groupOf = (btn: HTMLElement) => btn.closest('.tn-group')!
    // start: zamknięte
    await waitFor(() => expect(groupOf(ops).classList.contains('open')).toBe(false))
    // klik otwiera Operacje
    fireEvent.click(ops)
    await waitFor(() => expect(groupOf(ops).classList.contains('open')).toBe(true))
    // menu poza przewijanym paskiem (.tn-menu overflow-x) — fixed pod przyciskiem, nie przycięte
    expect((groupOf(ops).querySelector('.tn-drop') as HTMLElement).style.position).toBe('fixed')
    // klik w Analizę przełącza — Operacje się zamyka (jedno naraz)
    fireEvent.click(log)
    await waitFor(() => expect(groupOf(ops).classList.contains('open')).toBe(false))
    await waitFor(() => expect(groupOf(log).classList.contains('open')).toBe(true))
    // ponowny klik w otwartą zamyka
    fireEvent.click(log)
    await waitFor(() => expect(groupOf(log).classList.contains('open')).toBe(false))
  })

  it('rola customs: brak sekcji i brak Administracji (tylko Kolejka)', async () => {
    role = 'customs'
    mount()
    // poczekaj aż nawigacja się zbuduje (link kolejki istnieje dla każdej roli)
    await waitFor(() => expect(document.querySelector('a[href="/kolejka"]')).not.toBeNull(),
      { timeout: 5000 })
    // customs nie ma dostępu do Operacji/Logistyki ani administracji; Wiedza to baza
    // wewnętrzna (ACL-001, backend 403) — bez niej sekcja Analiza znika w ogóle
    expect(screen.queryByRole('button', { name: /Operacje/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Logistyka/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Analiza/ })).toBeNull()
    const hrefs = Array.from(document.querySelectorAll('a')).map(a => a.getAttribute('href'))
    expect(hrefs).not.toContain('/wiedza')
    expect(hrefs).not.toContain('/master-data')
    expect(hrefs).not.toContain('/wyceny')
    expect(hrefs).not.toContain('/administracja')
    expect(hrefs).not.toContain('/analityka')
  })
})
