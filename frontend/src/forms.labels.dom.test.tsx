// @vitest-environment jsdom
// Formularze (audyt UI B26/C22 — UX-002, UX-005): Specjalna troska ma etykiety nad każdym polem (bez
// placeholdera-etykiety i bez surowego klucza „note”), a w formularzu kontenera „Dokumenty kompletne”
// zamiast „Dokumenty TAK”, oba pola wyboru w jednym wierszu (Tranzyt nie wisi sam).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

const { apiGet } = vi.hoisted(() => ({
  apiGet: vi.fn((path: string) => Promise.resolve(
    path === '/api/customer-orders/responsibles' ? [{ id: 5, name: 'Anna Nowak' }]
      : path === '/api/companies' ? [{ id: 1, name: 'A', code: 'A', is_active: true }, { id: 2, name: 'B', code: 'B', is_active: true }]
        : [])),
}))
vi.mock('./api', () => ({
  api: { get: apiGet, post: vi.fn(), patch: vi.fn(), del: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ role: 'admin' }) }))
vi.mock('./userContext', () => ({ useUser: () => ({ role: 'admin' }) }))

import SpecialCarePage from './pages/SpecialCarePage'
import { ContainerFormModal } from './components'

afterEach(cleanup)

describe('formularze — etykiety i konwencje', () => {
  it('Specjalna troska: każde pole z widoczną etykietą nad polem, „Uwagi” zamiast „note”', async () => {
    const { container } = render(<SpecialCarePage />)
    await screen.findByRole('option', { name: 'Anna Nowak' })
    const form = container.querySelector('form')!
    const controls = [...form.querySelectorAll('input:not([type=checkbox]), select, textarea')]
    expect(controls.length).toBeGreaterThanOrEqual(8)
    for (const el of controls) {
      const label = el.closest('label.field')?.querySelector('.field-label')?.textContent
      expect(label, el.outerHTML).toBeTruthy()
      expect(el.getAttribute('placeholder')).not.toBe(label)
    }
    expect(screen.queryByText('note')).toBeNull()
    expect(screen.queryByPlaceholderText('note')).toBeNull()
    expect(screen.getByLabelText('Uwagi')).toBeTruthy()
  })

  it('formularz kontenera: „Dokumenty kompletne” i Tranzyt w jednym wierszu pól wyboru', () => {
    render(<ContainerFormModal dicts={{ suppliers: [], forwarders: [], warehouses: [], ports: [], carriers: [] }}
                               onSaved={() => {}} onClose={() => {}} />)
    expect(screen.queryByText(/Dokumenty TAK/)).toBeNull()
    const docs = screen.getByLabelText('Dokumenty kompletne')
    const transit = screen.getByLabelText('Tranzyt')
    const row = docs.closest('.form-checks')
    expect(row).not.toBeNull()
    expect(transit.closest('.form-checks')).toBe(row)
  })
})
