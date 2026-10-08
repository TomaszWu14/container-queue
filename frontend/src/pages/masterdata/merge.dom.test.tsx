// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { mdAt } from '../mdRoute.testutil'
import MasterDataPage from '../MasterDataPage'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('../../App', () => ({ useUser: () => ({ role: 'admin' }) }))

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../../api', () => ({
  api: { get: apiGet, post: apiPost, patch: vi.fn(), del: vi.fn(), upload: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))

const companies = [{ id: 1, name: 'Acme', code: 'ACME', is_active: true }]
const suppliers = [
  { id: 10, name: 'shangai', client_company_id: null, sap_code: '', country: '', address: '' },
  { id: 11, name: 'Shanghai', client_company_id: null, sap_code: '30001', country: 'CN', address: '' },
]

afterEach(() => { cleanup(); apiGet.mockReset(); apiPost.mockReset() })

describe('scalanie duplikatów dostawców (#20)', () => {
  it('dialog Scal z…: wybór celu i POST /merge', async () => {
    apiGet.mockImplementation((url: string) =>
      url.startsWith('/api/companies') ? Promise.resolve(companies)
        : url.startsWith('/api/suppliers/unmapped') ? Promise.resolve([])
        : url.startsWith('/api/suppliers') ? Promise.resolve(suppliers)
        : Promise.reject(new Error('unmocked ' + url)))
    apiPost.mockResolvedValue({ target_id: 11, repinned: { containers: 1 } })

    render(mdAt('dostawcy', <MasterDataPage />))
    await screen.findByText('shangai')

    fireEvent.click(screen.getAllByText('mdMerge')[0])   // wiersz „shangai" (id=10)
    await screen.findByText('mdMergeTitle')

    const select = screen.getByRole('dialog').querySelector('select') as HTMLSelectElement
    fireEvent.change(select, { target: { value: '11' } })
    fireEvent.click(screen.getByText('mdMergeDo'))

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/suppliers/10/merge', { target_id: 11 }))
  })
})
