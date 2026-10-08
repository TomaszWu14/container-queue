// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import SupplierMapsTab from './SupplierMapsTab'

// #12: słownik mapowań — lista z nazwami + dodanie wysyła supplier_id jako liczbę.
vi.mock('../../i18n', async (orig) => ({
  ...await orig<typeof import('../../i18n')>(), useT: () => (k: string) => k,
}))
vi.mock('../../App', () => ({ useUser: () => ({ role: 'purchasing' }) }))
const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../../api', () => ({ api: { get: apiGet, post: apiPost, del: vi.fn() }, errorMessage: String }))
afterEach(() => { cleanup(); apiGet.mockReset(); apiPost.mockReset() })

const COMPANIES = [{ id: 1, name: 'Acme', code: 'ZAR', is_active: true }]

describe('SupplierMapsTab', () => {
  it('listuje i dodaje mapowanie', async () => {
    apiGet.mockImplementation((u: string) => Promise.resolve(u.includes('suppliers')
      ? [{ id: 5, name: 'EMY' }]
      : [{ id: 9, company_id: 1, supplier_id: 5, supplier_code: 'A-1', ref_code: 'R100', note: '' }]))
    apiPost.mockResolvedValue({})
    const { container } = render(<SupplierMapsTab companies={COMPANIES} />)
    expect(await screen.findByText('R100')).toBeTruthy()
    await waitFor(() => expect(screen.getAllByText('EMY').length).toBeGreaterThan(0))
    const [comp, sup] = container.querySelectorAll('select')
    fireEvent.change(comp, { target: { value: 'ZAR' } })
    fireEvent.change(sup, { target: { value: '5' } })
    fireEvent.change(screen.getByPlaceholderText('smapSupplierCode'), { target: { value: 'B-2' } })
    fireEvent.change(screen.getByPlaceholderText('smapRefCode'), { target: { value: 'R200' } })
    fireEvent.submit(container.querySelector('form')!)
    expect(apiPost).toHaveBeenCalledWith('/api/supplier-material-maps',
      expect.objectContaining({ company_code: 'ZAR', supplier_id: 5, supplier_code: 'B-2', ref_code: 'R200' }))
  })
})
