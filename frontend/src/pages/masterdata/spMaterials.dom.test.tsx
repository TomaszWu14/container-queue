// @vitest-environment jsdom
// Strażnik (2026-09-29): zakładki pliku danych materiałowych jako osobne tabele + wyszukiwanie.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
const get = vi.fn()
vi.mock('../../api', () => ({ api: { get: (p: string) => get(p), upload: vi.fn() }, errorMessage: String }))

import SpMaterialsTab from './SpMaterialsTab'

afterEach(() => { cleanup(); get.mockReset() })

describe('SpMaterialsTab', () => {
  it('zakładka = tabela; przełączenie i wyszukiwanie pytają o właściwy arkusz', async () => {
    get.mockImplementation((path: string) => Promise.resolve(path === '/api/sp-materials/sheets'
      ? [{ name: 'Hierarchia produktów', rows: 2, filename: 'f.xlsm', imported_at: null },
         { name: 'BLOZ', rows: 1, filename: 'f.xlsm', imported_at: null }]
      : { headers: ['REF', 'KOD_CN'], total: 1, rows: [['AT-SGS-XL_1', '62101092']] }))
    render(<SpMaterialsTab />)
    expect(await screen.findByText('AT-SGS-XL_1')).toBeTruthy()
    expect(get).toHaveBeenCalledWith(expect.stringContaining('/sheets/Hierarchia%20produkt%C3%B3w?'))
    fireEvent.click(screen.getByRole('tab', { name: /BLOZ/ }))
    await waitFor(() => expect(get).toHaveBeenCalledWith(expect.stringContaining('/sheets/BLOZ?')))
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '6210' } })
    await waitFor(() => expect(get).toHaveBeenCalledWith(expect.stringContaining('q=6210')))
  })
})
