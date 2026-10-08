// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import SupplierResolvePanel from './SupplierResolvePanel'

// {n} zostawiony tylko w „Scal wszystkie”, żeby sprawdzić licznik
vi.mock('../../i18n', () => ({ useT: () => (key: string) => key === 'supResMergeAll' ? `${key} {n}` : key }))
const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast }) }))
const { apiGet, apiPost, apiPatch, apiDel } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiPatch: vi.fn(), apiDel: vi.fn() }))
vi.mock('../../api', () => ({
  api: { get: apiGet, post: apiPost, patch: apiPatch, del: apiDel, upload: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))

const brief = (id: number, name: string, sap = '', usage = 0) =>
  ({ id, name, sap_code: sap, country: 'CN', is_active: true, usage })
const plan = {
  merge_groups: [{ sap_code: '200', target: brief(2, 'Ningbo Tools', '200', 3),
                   sources: [brief(1, 'Ningbo Tools', '200', 1)] }],
  unresolved: [{ ...brief(5, 'NINGBO TOOLS'), suggestion: brief(2, 'Ningbo Tools', '200', 3) },
               { ...brief(6, 'Nikt', '', 2), suggestion: null }],
}
const suppliers = [
  { id: 2, name: 'Ningbo Tools', sap_code: '200', client_company_id: null, address: 'A', note: '', column_map: '' },
  { id: 6, name: 'Nikt', sap_code: '', client_company_id: null, address: 'Adres 6', note: 'n', column_map: '' },
]

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('Do rozstrzygnięcia', () => {
  it('scala wszystkie grupy i pojedynczego z podpowiedzią', async () => {
    apiGet.mockResolvedValue(plan)
    apiPost.mockResolvedValue({})
    const onChanged = vi.fn()
    render(<SupplierResolvePanel suppliers={suppliers as never} onChanged={onChanged} />)
    fireEvent.click(await screen.findByText('supResShow'))
    fireEvent.click(screen.getByText('supResMergeAll 1'))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/suppliers/resolve/apply', {}))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())

    const pick = screen.getByLabelText('mdMergePick: NINGBO TOOLS') as HTMLSelectElement
    expect(pick.value).toBe('2')
    fireEvent.click(screen.getAllByText('supResMerge')[0])
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/suppliers/5/merge', { target_id: 2 }))
  })

  it('nieaktywny zachowuje pola wiersza; usuwanie tylko bez powiązań', async () => {
    apiGet.mockResolvedValue(plan)
    apiPatch.mockResolvedValue({})
    render(<SupplierResolvePanel suppliers={suppliers as never} onChanged={() => {}} />)
    fireEvent.click(await screen.findByText('supResShow'))
    fireEvent.click(screen.getAllByText('supResInactive')[1])
    await waitFor(() => expect(apiPatch).toHaveBeenCalledWith('/api/suppliers/6', {
      name: 'Nikt', is_active: false, address: 'Adres 6', note: 'n', column_map: '' }))
    const del = screen.getAllByText('supResDelete') as HTMLButtonElement[]
    expect(del[0].disabled).toBe(false)   // NINGBO TOOLS: 0 użyć
    expect(del[1].disabled).toBe(true)    // Nikt: 2 użycia — tylko nieaktywny
  })

  it('grupa z 2 profilami: oznaczona, „Scal wszystkie” jej nie liczy', async () => {
    apiGet.mockResolvedValue({ ...plan, merge_groups: [
      ...plan.merge_groups,
      { sap_code: '300', target: brief(3, 'Solo', '300'), profile_conflict: true,
        sources: [brief(4, 'Solo', '300'), brief(7, 'Solo', '300')] }] })
    render(<SupplierResolvePanel suppliers={suppliers as never} onChanged={() => {}} />)
    fireEvent.click(await screen.findByText('supResShow'))
    expect(screen.getAllByText('supResProfileConflict')).toHaveLength(1)
    // 1 duplikat z grupy 200; 2 z grupy 300 (konflikt profili) nie wchodzą
    expect((screen.getByText('supResMergeAll 1') as HTMLButtonElement).disabled).toBe(false)
  })

  it('nieoczekiwany kształt odpowiedzi (ogólny mock listy dostawców) → brak panelu', async () => {
    apiGet.mockResolvedValue([{ id: 1, name: 'x' }])
    const { container } = render(<SupplierResolvePanel suppliers={[]} onChanged={() => {}} />)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/suppliers/resolve'))
    expect(container.textContent).toBe('')
  })

  it('kopie bez powiązań: podgląd (liczniki, próbka), potwierdzenie liczbą, usunięcie', async () => {
    const orphans = { count: 3, by_company: { ACME: 2, PT: 1 },
                       sample: [{ id: 10, name: 'Copy A', company_code: 'ACME' }] }
    apiGet.mockImplementation((url: string) =>
      Promise.resolve(url === '/api/suppliers/resolve/orphans' ? orphans
                                                                 : { merge_groups: [], unresolved: [] }))
    apiPost.mockResolvedValue({ deleted: 3 })
    const onChanged = vi.fn()
    render(<SupplierResolvePanel suppliers={[]} onChanged={onChanged} />)
    fireEvent.click(await screen.findByText('supResShow'))
    await screen.findByText('supResOrphansTitle')
    expect(screen.getByText('ACME: 2 · PT: 1')).toBeTruthy()
    // próbka ucięta (1 z 3) → „+N więcej”
    expect(screen.getByText(/supResOrphansSample/).textContent).toBe('supResOrphansSample supResOrphansMore')

    const btn = screen.getByText('supResOrphansDeleteBtn') as HTMLButtonElement
    expect(btn.disabled).toBe(true)   // liczba niewpisana lub błędna
    const input = screen.getByPlaceholderText('supResOrphansConfirmLabel')
    fireEvent.change(input, { target: { value: '2' } })
    expect(btn.disabled).toBe(true)   // zła liczba
    fireEvent.change(input, { target: { value: '3' } })
    expect(btn.disabled).toBe(false)
    fireEvent.click(btn)
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/suppliers/resolve/orphans/delete', {}))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
  })
})
