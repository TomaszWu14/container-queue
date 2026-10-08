// @vitest-environment jsdom
// Strażnik formularzy zakładek admina (2026-09-24): Anuluj przy dodawaniu czyści pola,
// przy edycji wraca do wartości rekordu (także Esc); przy zmianach pyta „porzucić?".
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
const { apiGet, apiPatch } = vi.hoisted(() => ({
  apiGet: vi.fn(() => Promise.resolve([{ id: 1, name: 'Acme', code: 'ZAR', is_active: true, avizo_cc: 'a@x.pl' }])),
  apiPatch: vi.fn(() => Promise.resolve({})),
}))
vi.mock('../../api', () => ({ api: { get: apiGet, patch: apiPatch, post: vi.fn() }, errorMessage: String }))

import CompaniesTab from './CompaniesTab'

afterEach(() => { cleanup(); vi.restoreAllMocks(); apiPatch.mockClear() })

describe('formularze zakładek admina', () => {
  it('Anuluj przy dodawaniu: pojawia się po wpisaniu, pyta i czyści pola', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<CompaniesTab />)
    await screen.findByText('Acme')
    expect(screen.queryByText('cancel')).toBeNull()
    const name = screen.getByPlaceholderText('name') as HTMLInputElement
    fireEvent.change(name, { target: { value: 'Nowa' } })
    fireEvent.click(screen.getByText('cancel'))
    expect(window.confirm).toHaveBeenCalledWith('discardChanges')
    await waitFor(() => expect(name.value).toBe(''))
  })

  it('edycja: Anuluj po lewej od Zapisz, Esc porzuca zmianę i przywraca wartość rekordu', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<CompaniesTab />)
    fireEvent.click(await screen.findByText('edit'))
    const btns = screen.getAllByRole('button').map(b => b.textContent)
    expect(btns.indexOf('cancel')).toBeLessThan(btns.indexOf('save'))
    fireEvent.change(screen.getByLabelText('avizoCc'), { target: { value: 'zmiana@x.pl' } })
    await act(async () => { fireEvent.keyDown(document, { key: 'Escape' }) })
    expect(window.confirm).toHaveBeenCalledWith('discardChanges')
    expect(screen.getByText('a@x.pl')).toBeTruthy()
    expect(apiPatch).not.toHaveBeenCalled()
  })
})
