// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../i18n', () => ({ useT: () => (k: string) => k }))
const apiGet = vi.fn().mockResolvedValue({ date_from: '2026-09-05' })
const apiUpload = vi.fn().mockResolvedValue({ dry_run: true, containers: 3, changed: 2, skipped_old: 1 })
vi.mock('../api', () => ({
  api: { get: (...a: unknown[]) => apiGet(...a), upload: (...a: unknown[]) => apiUpload(...a) },
  errorMessage: (e: unknown) => String(e),
}))

import SyncUploadModal from './SyncUploadModal'

afterEach(() => { cleanup(); apiGet.mockClear(); apiUpload.mockClear() })

describe('SyncUploadModal — filtr od daty rozładunku (queue-sync)', () => {
  it('pokazuje pole daty i prefilluje je z GET queue-sync-date-from', async () => {
    render(<SyncUploadModal companyCode="BOREALIS" endpoint="/api/import/queue-sync"
                            titleKey="queueSync" hintKey="queueSyncHint"
                            onDone={() => {}} onClose={() => {}} />)
    expect(screen.getByText('queueDateFrom')).toBeTruthy()
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith(
      '/api/import/queue-sync-date-from?company_code=BOREALIS'))
    const input = screen.getByText('queueDateFrom').querySelector('input') as HTMLInputElement
    await waitFor(() => expect(input.value).toBe('2026-09-05'))
  })

  it('nie pokazuje pola daty dla innych endpointów (ETD)', () => {
    render(<SyncUploadModal companyCode="BOREALIS" endpoint="/api/import/purchase-orders"
                            titleKey="etdImport" hintKey="etdImportHint"
                            onDone={() => {}} onClose={() => {}} />)
    expect(screen.queryByText('queueDateFrom')).toBeNull()
  })

  it('przekazuje date_from w query przy uploadzie i pokazuje skipped_old', async () => {
    render(<SyncUploadModal companyCode="BOREALIS" endpoint="/api/import/queue-sync"
                            titleKey="queueSync" hintKey="queueSyncHint"
                            onDone={() => {}} onClose={() => {}} />)
    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    const input = screen.getByText('queueDateFrom').querySelector('input') as HTMLInputElement
    fireEvent.change(input, { target: { value: '2026-09-10' } })

    const file = new File(['x'], 'q.xlsx')
    const fileInput = screen.getByLabelText('importFileLbl') as HTMLInputElement   // ukryty input FilePicker
    fireEvent.change(fileInput, { target: { files: [file] } })

    fireEvent.click(screen.getByText('importPreviewBtn'))
    await waitFor(() => expect(apiUpload).toHaveBeenCalled())
    const [path] = apiUpload.mock.calls[0]
    expect(path).toContain('date_from=2026-09-10')
    expect(await screen.findByText((_, el) => el?.textContent === '1 queueSkippedOld')).toBeTruthy()
  })

  it('0 zmian → powód i podpowiedź o pominiętych starszych; zmiana daty wraca do podglądu', async () => {
    apiUpload.mockResolvedValueOnce({ dry_run: true, containers: 460, changed: 0, skipped_old: 1664 })
    render(<SyncUploadModal companyCode="ACME" endpoint="/api/import/queue-sync"
                            titleKey="queueSync" hintKey="queueSyncHint"
                            onDone={() => {}} onClose={() => {}} />)
    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    fireEvent.change(screen.getByLabelText('importFileLbl'), { target: { files: [new File(['x'], 'q.xlsx')] } })
    fireEvent.click(screen.getByText('importPreviewBtn'))
    const note = await screen.findByRole('status')
    expect(note.textContent).toContain('importNoChanges')
    expect(note.textContent).toContain('queueSkippedOldHint')

    const input = screen.getByText('queueDateFrom').querySelector('input') as HTMLInputElement
    fireEvent.change(input, { target: { value: '2026-01-01' } })
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.getByText('importPreviewBtn')).toBeTruthy()
  })
})
