// @vitest-environment jsdom
// Edytor kolorów: firmowe zapisuje admin przez API; osobiste idą do profilu konta (setPref), bez API zapisu.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../../../i18n', () => ({ useT: () => (key: string) => key }))
const get = vi.fn(), put = vi.fn(), setPref = vi.fn()
vi.mock('../../../api', () => ({
  api: { get: (p: string) => get(p), put: (p: string, b: unknown) => put(p, b) }, errorMessage: String,
}))
vi.mock('../../../prefs', () => ({ setPref: (k: string, v: string) => setPref(k, v), cancelPendingPrefs: vi.fn() }))

import { ColorsEditor } from './ColorsEditor'

afterEach(() => { cleanup(); get.mockReset(); put.mockReset(); setPref.mockReset(); localStorage.clear() })

const openFirst = async () => {
  fireEvent.click((await screen.findAllByRole('button', { name: /colTokRow/ }))[0])   // tło wiersza DLT
  fireEvent.change(screen.getByLabelText('colHex'), { target: { value: '#4d3a12' } })
}

describe('ColorsEditor', () => {
  it('firmowe: wybór koloru → podgląd i zapis przez API admina', async () => {
    get.mockResolvedValue({ light: {}, dark: {} })
    put.mockImplementation((_p: string, b: unknown) => Promise.resolve(b))
    render(<ColorsEditor scope="company" />)
    await openFirst()
    expect((screen.getByRole('img') as HTMLElement).style.getPropertyValue('--kq-row-dlt')).toBe('#4d3a12')
    expect(screen.getByText('colChanged')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'colSave' }))
    await waitFor(() => expect(put).toHaveBeenCalledWith('/api/admin/theme-colors',
      { light: { '--kq-row-dlt': '#4d3a12' }, dark: {} }))
    expect(await screen.findByRole('status')).toBeTruthy()
  })

  it('osobiste: zapis do profilu konta, firmowe tylko jako punkt odniesienia', async () => {
    get.mockResolvedValue({ light: { '--bg': '#101010' }, dark: {} })
    render(<ColorsEditor scope="personal" />)
    expect(await screen.findByText('colMyTitle')).toBeTruthy()
    await openFirst()
    fireEvent.click(screen.getByRole('button', { name: 'colSave' }))
    await waitFor(() => expect(setPref).toHaveBeenCalledWith('userThemeColors',
      JSON.stringify({ light: { '--kq-row-dlt': '#4d3a12' }, dark: {} })))
    expect(put).not.toHaveBeenCalled()
  })
})
