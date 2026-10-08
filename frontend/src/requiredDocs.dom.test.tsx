// @vitest-environment jsdom
// Karta dostawcy → „Wymagane dokumenty” (spec 2026-10-06 decyzja 16): admin zapisuje własny zestaw
// kafelków i przywraca domyślne (codes: null); logistyka tylko widzi (pola zablokowane).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

let USER: { role: string } = { role: 'admin' }
let PROFILE: Record<string, unknown>
const putMock = vi.fn((_p: string, body: { codes: string[] | null }) => {
  PROFILE = { ...PROFILE, required_docs: body.codes }
  return Promise.resolve(PROFILE)
})

vi.mock('./api', () => ({
  api: {
    get: () => Promise.resolve(PROFILE),
    put: (p: string, b: { codes: string[] | null }) => putMock(p, b),
  },
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => USER }))

import DocProfileCard from './pages/supplierProfile/DocProfileCard'
import { ToastProvider } from './feedback'

const BASE = {
  id: null, supplier_id: 3, status: 'draft', currency: '', doc_language: '', keywords: [],
  ci_map: {}, pl_map: {}, ref_kind: 'ours', split_marker: '', tol_amount_pct: 0.5, tol_qty_pct: 0,
  samples: [], required_docs: null,
}

const renderCard = () =>
  render(<ToastProvider><DocProfileCard supplierId={3} supplierName="Glove Co" /></ToastProvider>)

describe('Wymagane dokumenty dostawcy', () => {
  beforeEach(() => { USER = { role: 'admin' }; PROFILE = { ...BASE }; putMock.mockClear() })
  afterEach(cleanup)

  it('admin zapisuje własny zestaw i przywraca domyślne', async () => {
    renderCard()
    const pi = await screen.findByRole<HTMLInputElement>('checkbox', { name: /PI · Proforma/ })
    expect(pi.checked).toBe(true)                                 // domyślnie wszystkie
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Przywróć domyślne' }).disabled).toBe(true)
    fireEvent.click(pi)
    fireEvent.click(screen.getByRole('checkbox', { name: /PW · Zwolnienie/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz wymagane' }))
    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/suppliers/3/required-docs',
      { codes: ['CI', 'PL', 'BL', 'SAD_DRAFT', 'SAD_PZ'] }))
    expect(await screen.findByText('własny zestaw')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Przywróć domyślne' }))
    await waitFor(() => expect(putMock).toHaveBeenLastCalledWith('/api/suppliers/3/required-docs', { codes: null }))
    await waitFor(() => expect(screen.getByRole<HTMLInputElement>('checkbox', { name: /PI · Proforma/ }).checked).toBe(true))
  })

  it('logistyka widzi zestaw bez edycji', async () => {
    USER = { role: 'logistics' }
    PROFILE = { ...BASE, required_docs: ['BL'] }
    renderCard()
    const bl = await screen.findByRole<HTMLInputElement>('checkbox', { name: /BL · Konosament/ })
    expect(bl.checked).toBe(true)
    expect(bl.matches(':disabled')).toBe(true)   // fieldset disabled
    expect(screen.getByRole<HTMLInputElement>('checkbox', { name: /CI · Faktura/ }).checked).toBe(false)
    expect(screen.queryByRole('button', { name: 'Zapisz wymagane' })).toBeNull()
  })
})
