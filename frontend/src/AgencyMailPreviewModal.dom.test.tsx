// @vitest-environment jsdom
// Podgląd maila do agencji: odbiorcy, ostrzeżenia, każdy załącznik do otwarcia, .eml dopiero z podglądu.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (k: string) => k }))
const get = vi.fn()
const download = vi.fn().mockResolvedValue(undefined)
vi.mock('./api', () => ({
  api: { get: (p: string) => get(p) },
  downloadFile: (u: string, n: string) => download(u, n),
  errorMessage: (e: unknown) => String(e),
}))

import { AgencyMailPreviewModal } from './AgencyMailPreviewModal'
import type { InvoiceBatch } from './types'

const batch = { id: 3, attachment_id: 41 } as InvoiceBatch
const preview = {
  to: ['odprawy@agencja.pl'], cc: ['zespol@firma.pl'], subject: 'Faktury — HLBU2672415 — ACME', agency: 'Delta',
  body: 'Dzień dobry,\n\nZałączniki:', warnings: ['1 faktur(y) niezatwierdzone — nie trafią do maila: CBN-E20260692'],
  attachments: [
    { name: 'Faktury_HLBU2672415.xlsx', size: 9000, kind: 'excel', job_id: null },
    { name: 'kartoteka_symboli_HLBU2672415.xlsx', size: 6000, kind: 'symbols', job_id: null },
    { name: 'CI.pdf', size: 3_900_000, kind: 'invoice', job_id: 77 },
  ],
}

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('AgencyMailPreviewModal', () => {
  it('pokazuje odbiorców, ostrzeżenia i otwiera każdy załącznik; .eml z podglądu', async () => {
    get.mockResolvedValue(preview)
    const onClose = vi.fn()
    render(<AgencyMailPreviewModal batch={batch} containerNo="HLBU2672415" onClose={onClose} />)
    expect(await screen.findByText('odprawy@agencja.pl')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('niezatwierdzone')
    expect(screen.getByText('3.7 MB')).toBeTruthy()
    const [excel, symbols, pdf] = screen.getAllByText('mailPrevOpen')
    fireEvent.click(excel); fireEvent.click(symbols); fireEvent.click(pdf)
    expect(download.mock.calls.map(c => c[0])).toEqual([
      '/api/attachments/41/download', '/api/invoice-batches/3/symbols.xlsx', '/api/invoice-jobs/77/pdf'])
    fireEvent.click(screen.getByText('mailPrevDownload'))
    await waitFor(() => expect(download).toHaveBeenCalledWith('/api/invoice-batches/3/agency-mail.eml', 'faktury_HLBU2672415.eml'))
    expect(onClose).toHaveBeenCalled()
  })

  it('bez ostrzeżeń: „Komplet”; błąd 409 (np. brak agencji) widoczny, .eml zablokowany', async () => {
    get.mockResolvedValueOnce({ ...preview, warnings: [] })
    render(<AgencyMailPreviewModal batch={batch} containerNo="X" onClose={() => {}} />)
    expect(await screen.findByText(/mailPrevAllOk/)).toBeTruthy()
    cleanup()
    get.mockRejectedValueOnce(new Error('Kontener nie ma przypisanej agencji celnej.'))
    render(<AgencyMailPreviewModal batch={batch} containerNo="X" onClose={() => {}} />)
    expect(await screen.findByText(/agencji celnej/)).toBeTruthy()
    expect((screen.getByText('mailPrevDownload') as HTMLButtonElement).disabled).toBe(true)
  })
})
