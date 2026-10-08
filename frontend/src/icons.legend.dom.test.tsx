// @vitest-environment jsdom
// Ikony i legenda (audyt UI B28/A16/A7 — UX-003, UX-012, UX-020):
// - Użytkownicy: w każdym wierszu te same sloty akcji w tej samej kolejności (brak e-maila = nieaktywna
//   koperta z podpowiedzią, nie przesunięte przyciski), ikony z nazwą dla czytnika, bez zawijania,
// - kolejka: pasek etapu przy wierszu ma podpowiedź, a stopka legendę kodów kolorów,
// - pulpit: na tablecie kolumny Spółka/Port chowane (akcja „Szczegóły” mieści się bez przewijania).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { readAppCss } from './appCss.testutil'

const USERS = [
  { id: 1, login: 'admin', full_name: 'Admin', email: '', role: 'admin', company_id: null, is_active: true,
    view_all_companies: true, last_seen: null, totp_enabled: false },
  { id: 2, login: 'demo', full_name: 'Demo', email: 'demo@x.pl', role: 'logistics', company_id: 1, is_active: true,
    view_all_companies: true, last_seen: null, totp_enabled: false },
]
vi.mock('./api', () => ({
  api: { get: vi.fn((p: string) => Promise.resolve(p === '/api/users' ? USERS : [])), post: vi.fn(), patch: vi.fn(), del: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ id: 1, role: 'admin' }) }))

import UsersTab from './pages/admin/UsersTab'

afterEach(cleanup)

describe('ikony akcji i legenda', () => {
  it('Użytkownicy: identyczne sloty akcji, koperta bez e-maila nieaktywna, ikony z aria-label', async () => {
    render(<UsersTab />)
    await screen.findByText('demo')
    const rows = [...document.querySelectorAll('tbody tr')].filter(r => r.querySelector('.row-actions'))
    expect(rows).toHaveLength(2)
    const slots = rows.map(r => [...r.querySelectorAll('.row-actions button')].map(b => b.getAttribute('aria-label') ?? b.textContent))
    expect(slots[0]).toEqual(slots[1])
    const mail = rows[0].querySelector('.row-actions button') as HTMLButtonElement
    expect(mail.disabled).toBe(true)
    expect(mail.title).toBe('Brak adresu e-mail')
    for (const b of rows[1].querySelectorAll('.row-actions button')) {
      if (!b.textContent?.trim()) expect(b.getAttribute('aria-label')).toBeTruthy()
    }
    expect(readAppCss()).toMatch(/\.row-actions \{[^}]*flex-wrap: nowrap/)
  })

  it('pulpit: Spółka/Port oznaczone do ukrycia na tablecie (≤ 1024 px)', async () => {
    const src = (await import('./pages/DashboardPage.tsx?raw')).default as string
    expect(src.match(/className="hide-md"/g)?.length).toBeGreaterThanOrEqual(4)   // 2 × th + 2 × td
    expect(readAppCss()).toMatch(/@media \(max-width: 1024px\) \{[^}]*\.hide-md \{ display: none; \}/)
  })
})
