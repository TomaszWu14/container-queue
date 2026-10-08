// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import UnmappedSuppliersPanel from './UnmappedSuppliersPanel'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast }) }))

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../../api', () => ({
  api: { get: apiGet, post: apiPost, patch: vi.fn(), del: vi.fn(), upload: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))

// kartoteka (client_company_id null) + nadawcy spółek-klientów 1 i 2
const suppliers = [
  { id: 11, name: 'Shanghai Co', client_company_id: null, is_active: true },
  { id: 12, name: 'Obcy', client_company_id: 2, is_active: true },
  { id: 13, name: 'Nadawca T', client_company_id: 1, is_active: true },
]

afterEach(() => { cleanup(); apiGet.mockReset(); apiPost.mockReset(); showToast.mockReset() })

describe('panel Do zmapowania', () => {
  it('spółka z materiałami mapuje na kartotekę, klient na swoich nadawców; alias z company_id', async () => {
    apiGet.mockResolvedValue([
      { name: 'SHANGHAI CO., LTD', company_id: 3, containers: 3, catalog: true },
      { name: 'T-plik', company_id: 1, containers: 1, catalog: false },
    ])
    apiPost.mockResolvedValue({ alias: {}, assigned: 3 })
    const onNew = vi.fn()
    render(<UnmappedSuppliersPanel suppliers={suppliers as never} isAdmin onNew={onNew} />)
    await screen.findByText('SHANGHAI CO., LTD')
    expect(apiGet).toHaveBeenCalledWith('/api/suppliers/unmapped')

    const sel = screen.getByLabelText('supPick: SHANGHAI CO., LTD') as HTMLSelectElement
    expect([...sel.options].map(o => o.value)).toEqual(['', '11'])
    const selT = screen.getByLabelText('supPick: T-plik') as HTMLSelectElement
    expect([...selT.options].map(o => o.value)).toEqual(['', '13'])

    fireEvent.change(sel, { target: { value: '11' } })
    fireEvent.click(screen.getAllByText('supMap')[0])
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/suppliers/11/aliases', { alias: 'SHANGHAI CO., LTD', company_id: 3 }))
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('supMappedN'))

    fireEvent.click(screen.getAllByText('supNewFromName')[0])
    expect(onNew).toHaveBeenCalledWith(
      { name: 'SHANGHAI CO., LTD', company_id: 3, containers: 3, catalog: true })
  })

  it('bez nazw do zmapowania panel znika (czyszczenie słownika usunięte)', async () => {
    apiGet.mockResolvedValue([])
    const { container } = render(<UnmappedSuppliersPanel suppliers={[]} isAdmin onNew={() => {}} />)
    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    expect(container.textContent).toBe('')
    expect(screen.queryByText('supPurgeBtn')).toBeNull()
  })
})
