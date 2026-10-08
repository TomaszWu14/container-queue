// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import QualityTab from './QualityTab'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

const { apiGet, apiUpload } = vi.hoisted(() => ({ apiGet: vi.fn(), apiUpload: vi.fn() }))
vi.mock('../../api', () => ({
  api: { get: apiGet, upload: apiUpload },
  errorMessage: (e: unknown) => String(e),
}))

const payload = {
  stale_import_days: 14,
  imports: [
    { type: 'marm', last_at: '2026-09-18T00:00:00', age_days: 1, stale: false },
    { type: 'ekko', last_at: null, age_days: null, stale: true },
  ],
  issues: [
    { key: 'suppliers_no_sap', tab: 'suppliers', count: 2,
      items: [{ id: 1, label: 'Alfa' }, { id: 2, label: 'Beta' }] },
    { key: 'cports_no_coords', tab: 'cports', count: 0, items: [] },
  ],
}

const companies = [{ id: 1, name: 'Acme', code: 'ACME', is_active: true }]

afterEach(() => { cleanup(); apiGet.mockReset(); apiUpload.mockReset() })

describe('QualityTab', () => {
  it('pokazuje świeżość importów, problemy z licznikiem i link do zakładki', async () => {
    apiGet.mockResolvedValue(payload)
    const onGoTab = vi.fn()
    render(<QualityTab companies={companies as never} onGoTab={onGoTab} />)

    await screen.findByText('qSuppliersNoSap')
    expect(screen.getByText(/: 2/)).toBeTruthy()          // licznik problemu
    expect(screen.getByText('qStale')).toBeTruthy()       // EKKO nigdy → stęchły
    expect(screen.getByText('qNever')).toBeTruthy()
    expect(screen.queryByText('qCportsNoCoords')).toBeNull()  // count=0 ukryty
    expect(screen.getByText('Alfa')).toBeTruthy()         // lista pozycji problemu

    fireEvent.click(screen.getByText('qGoTab'))
    expect(onGoTab).toHaveBeenCalledWith('suppliers')
  })

  it('dropzone: dry_run → podgląd → potwierdzenie importu', async () => {
    apiGet.mockResolvedValue(payload)
    apiUpload.mockResolvedValue({ detected: 'marm', counts: { new: 5 } })
    render(<QualityTab companies={companies as never} onGoTab={() => {}} />)
    await screen.findByText('qUpload')

    const file = new File(['x'], 'marm.xlsx')
    const input = document.querySelector('input[type=file]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [file] } })

    await screen.findByText('qConfirmImport')
    expect(apiUpload).toHaveBeenCalledWith(
      expect.stringContaining('dry_run=true'), file)

    fireEvent.click(screen.getByText('qConfirmImport'))
    await waitFor(() => expect(apiUpload).toHaveBeenCalledWith(
      expect.stringContaining('dry_run=false'), file))
  })

  it('EKKO/MARM z brakującymi rekordami: checkbox „pełny eksport” → full_export=true (DATA-003)', async () => {
    apiGet.mockResolvedValue(payload)
    apiUpload.mockResolvedValue({ detected: 'marm', counts: { new: 0, disappeared: 3 } })
    render(<QualityTab companies={companies as never} onGoTab={() => {}} />)
    await screen.findByText('qUpload')
    const file = new File(['x'], 'marm.xlsx')
    fireEvent.change(document.querySelector('input[type=file]') as HTMLInputElement,
                     { target: { files: [file] } })

    fireEvent.click(await screen.findByLabelText('sapFullExport'))
    fireEvent.click(screen.getByText('qConfirmImport'))
    await waitFor(() => expect(apiUpload).toHaveBeenCalledWith(
      expect.stringMatching(/dry_run=false.*full_export=true/), file))
  })
})
