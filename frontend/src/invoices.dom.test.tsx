// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { Container, InvoiceBatch, InvoiceJobDetail } from './types'

const container = { id: 7, container_no: 'CMAU8963315' } as unknown as Container

const batch: InvoiceBatch = {
  id: 3, container_id: 7, supplier_id: 1, supplier_name: 'Shieldco', total: 1, confirmed: 0,
  errors: 0, ready: false, excel_current: false, attachment_id: null, attachment_filename: null,
  created_at: '2026-09-17T10:00:00', updated_at: '2026-09-17T10:00:00',
  jobs: [
    { id: 11, batch_id: 3, filename: 'cipl.pdf', doc_kind: 'invoice', status: 'extracted', error: '',
      invoice_number: 'FV/1', container_no: 'CMAU8963315', delivery_terms: 'FOB', page_from: 1,
      page_to: 2, ocr_used: true, items_count: 2, updated_at: '2026-09-17T10:00:00' },
    { id: 12, batch_id: 3, filename: 'cipl.pdf', doc_kind: 'packing_list', status: 'packing_list',
      error: '', invoice_number: '', container_no: '', delivery_terms: '', page_from: 3, page_to: 3,
      ocr_used: false, items_count: 0, updated_at: '2026-09-17T10:00:00' },
  ],
}

const detail: InvoiceJobDetail = {
  ...batch.jobs[0],
  items: [
    { id: 1, line_no: 1, raw_ref: 'NL753-S-40', descr: 'Catheter', qty: '1000', uom_src: 'PCS',
      net_amount: '250', amount: '250', weight_net: '12.5', weight_gross: '13.2', cartons: '3',
      weight_source: 'pl', master_ref: 'NL753-S-40', name_pl: 'Cewnik', tariff_cn: '9018', sent: true,
      uom_factor: '1', match_status: 'matched', match_source: 'rules', ml_suggestion: '',
      ml_confidence: null, skipped: false },
    { id: 2, line_no: 2, raw_ref: 'MSK', descr: 'Mask', qty: '20', uom_src: 'CTN', net_amount: '200',
      amount: '200', weight_net: '', weight_gross: '', cartons: '', weight_source: 'brak',
      master_ref: '', name_pl: '', tariff_cn: '', sent: false, uom_factor: '',
      match_status: 'ambiguous', match_source: '', ml_suggestion: 'MSK2', ml_confidence: 0.62,
      skipped: false },
  ],
}

const { apiGet, apiPut, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
  apiPost: vi.fn(() => Promise.resolve({})),
}))

vi.mock('./api', () => ({
  api: { get: apiGet, put: apiPut, post: apiPost, del: vi.fn(), upload: vi.fn() },
  downloadFile: vi.fn(),
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))
vi.mock('./i18n', async importOriginal => {
  const actual = await importOriginal<typeof import('./i18n')>()
  return { ...actual, useT: () => (key: string) => key }
})
vi.mock('./dates', () => ({ formatDateTime: (s: string) => s }))

import { InvoiceBatchesPanel } from './InvoiceBatchesPanel'
import { downloadFile } from './api'

describe('InvoiceBatchesPanel', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('lists documents with status and opens review for the invoice', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/api/containers/7/invoice-batches') return Promise.resolve([batch])
      if (url === '/api/invoice-jobs/11') return Promise.resolve(detail)
      return Promise.reject(new Error(`unexpected ${url}`))
    })
    render(<InvoiceBatchesPanel container={container} />)
    await screen.findByText('invStatus_extracted')
    expect(screen.getByText('invStatus_packing_list')).toBeTruthy()
    expect(screen.getByText(/0\/1 invConfirmed/)).toBeTruthy()
    // brak zatwierdzonych → brak przycisku generowania Excela
    expect(screen.queryByText('invGenerateExcel')).toBeNull()

    fireEvent.click(screen.getByText('invReview'))
    await screen.findByText('Cewnik')
    expect(screen.getByText('invAmbiguous')).toBeTruthy()
    expect(screen.getByText('invAmbiguousHint')).toBeTruthy()

    // zatwierdzenie odbite przez backend (409) — komunikat widoczny, modal zostaje
    apiPut.mockRejectedValueOnce(new Error('Rozstrzygnij niejednoznaczne pozycje'))
    fireEvent.click(screen.getByText('invConfirm'))
    await screen.findByText('Rozstrzygnij niejednoznaczne pozycje')
    expect(apiPut).toHaveBeenCalledWith('/api/invoice-jobs/11/review', expect.objectContaining({
      confirm: true, invoice_number: 'FV/1',
      items: expect.arrayContaining([expect.objectContaining({ id: 2, master_ref: '' })]),
    }))

    // sugestia ML widoczna z pewnością; „Zastosuj” wpisuje ją w REF master
    expect(screen.getByText('(62%)', { exact: false })).toBeTruthy()
    expect(screen.getAllByText('invOcr').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByText('invMlApply'))
    expect((screen.getByDisplayValue('MSK2') as HTMLInputElement).className).toContain('invalid')
    apiPut.mockResolvedValueOnce({ ...detail, status: 'confirmed' })
    fireEvent.click(screen.getByText('invConfirm'))
    await waitFor(() => expect(screen.queryByText('invReviewTitle', { exact: false })).toBeNull())
    expect(apiPut).toHaveBeenLastCalledWith('/api/invoice-jobs/11/review', expect.objectContaining({
      items: expect.arrayContaining([expect.objectContaining({ id: 2, master_ref: 'MSK2' })]),
    }))
  })

  it('offers Excel generation and download once confirmed', async () => {
    const ready = { ...batch, confirmed: 1, ready: true, excel_current: false, attachment_id: 99,
      attachment_filename: 'faktury.xlsx', jobs: [{ ...batch.jobs[0], status: 'confirmed' as const }] }
    apiGet.mockResolvedValue([ready])
    render(<InvoiceBatchesPanel container={container} />)
    await screen.findByText('invoicesReady')
    fireEvent.click(screen.getByText('invGenerateExcel'))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/invoice-batches/3/export?partial=false', {}))
    // Excel z poprzedniego eksportu jest nieaktualny — przycisk pobierania to sygnalizuje
    expect(screen.getByText(/downloadExcel \(invExcelStaleShort\)/)).toBeTruthy()
    // szkic maila do agencji zablokowany, dopóki Excel nieaktualny
    expect((screen.getByText('invAgencyMail') as HTMLButtonElement).disabled).toBe(true)
  })

  it('XML do WinSAD: pobiera SAD_<kontener>.xml, 409 pokazany w panelu', async () => {
    const current = { ...batch, confirmed: 1, ready: true, excel_current: true, attachment_id: 99,
      attachment_filename: 'faktury.xlsx', jobs: [{ ...batch.jobs[0], status: 'confirmed' as const }] }
    apiGet.mockResolvedValue([current])
    vi.mocked(downloadFile).mockRejectedValueOnce(new Error('1 pozycji nie trafi do XML'))
    render(<InvoiceBatchesPanel container={container} />)
    fireEvent.click(await screen.findByText('invSadueXml'))
    expect(downloadFile).toHaveBeenCalledWith('/api/invoice-batches/3/sadue.xml', 'SAD_CMAU8963315.xml')
    expect(await screen.findByText('1 pozycji nie trafi do XML')).toBeTruthy()
  })

  it('agency mail: opens the preview first, .eml only from the preview; 409 shown in the preview', async () => {
    const current = { ...batch, confirmed: 1, ready: true, excel_current: true, attachment_id: 99,
      attachment_filename: 'faktury.xlsx', jobs: [{ ...batch.jobs[0], status: 'confirmed' as const }] }
    const preview = { to: ['a@agencja.pl'], cc: [], subject: 'Faktury', body: '', agency: 'X', warnings: [],
      attachments: [{ name: 'faktury.xlsx', size: 10, kind: 'excel', job_id: null }] }
    apiGet.mockImplementation((url: string) => Promise.resolve(
      url.endsWith('/agency-mail/preview') ? preview : url.includes('invoice-batches') ? [current] : []))
    render(<InvoiceBatchesPanel container={container} />)
    const button = await screen.findByText('invAgencyMail') as HTMLButtonElement
    expect(button.disabled).toBe(false)
    fireEvent.click(button)
    expect(await screen.findByText('a@agencja.pl')).toBeTruthy()
    expect(downloadFile).not.toHaveBeenCalled()             // nic nie pobiera się „w ciemno”
    fireEvent.click(screen.getByText('mailPrevDownload'))
    await waitFor(() => expect(downloadFile).toHaveBeenCalledWith(
      '/api/invoice-batches/3/agency-mail.eml', 'faktury_CMAU8963315.eml'))
    apiGet.mockImplementation((url: string) => url.endsWith('/agency-mail/preview')
      ? Promise.reject(new Error('Agencja X nie ma adresu e-mail.'))
      : Promise.resolve(url.includes('invoice-batches') ? [current] : []))
    fireEvent.click(button)
    await screen.findByText('Agencja X nie ma adresu e-mail.')
  })
})

describe('InvoiceBatchesPanel — pominięte dokumenty i numer faktury', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('shows Restore instead of counts for an ignored invoice and calls reprocess', async () => {
    const ignored = { ...batch, total: 0,
      jobs: [{ ...batch.jobs[0], status: 'ignored' as const, items_count: 0 }, batch.jobs[1]] }
    apiGet.mockResolvedValue([ignored])
    apiPost.mockResolvedValue({})
    render(<InvoiceBatchesPanel container={container} />)
    await screen.findByText('invStatus_ignored')
    expect(screen.queryByText(/refRows/)).toBeNull()
    expect(screen.getAllByText('invIgnore')).toHaveLength(1)   // tylko packing lista (faktura już pominięta)
    fireEvent.click(screen.getByText('invRestore'))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/invoice-jobs/11/reprocess', {}))
  })

  it('disables Confirm until the invoice number is filled in', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/api/containers/7/invoice-batches') return Promise.resolve([batch])
      if (url === '/api/invoice-jobs/11') return Promise.resolve({ ...detail, invoice_number: '' })
      return Promise.reject(new Error(`unexpected ${url}`))
    })
    render(<InvoiceBatchesPanel container={container} />)
    await screen.findByText('invReview')
    fireEvent.click(screen.getByText('invReview'))
    await screen.findByText('Cewnik')
    const confirm = screen.getByText('invConfirm') as HTMLButtonElement
    expect(confirm.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('invInvoiceNo'), { target: { value: 'FV/9' } })
    expect((screen.getByText('invConfirm') as HTMLButtonElement).disabled).toBe(false)
  })
})
