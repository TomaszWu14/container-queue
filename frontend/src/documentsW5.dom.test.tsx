// @vitest-environment jsdom
// W5 dokumenty: panel propozycji (31), raport rozjazdów (33/34), podgląd szablonu (36)
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { AttachmentSuggestion, CompareReport, Container, InvoiceJob } from './types'

const container = { id: 7, container_no: 'CMAU8963315' } as unknown as Container

const suggestion: AttachmentSuggestion = {
  id: 1, job_id: 11, container_id: 7, doc_kind: 'invoice', status: 'proposed',
  document_type_id: null, attachment_id: null, created_at: '2026-09-18T10:00:00',
  filename: 'cipl.pdf', invoice_number: 'FV/1', page_from: 1, page_to: 2,
  container_no: 'CMAU8963315',
}

const report: CompareReport = {
  job_id: 11, kind: 'invoice', mismatches: 1, invoice_total: '450.00', po_total: '1000.00',
  diff_pct: 55, tolerance_pct: 2, exceeded: true,
  rows: [
    { ref: 'NL753-S-40', doc_qty: '900', sys_qty: '1000', status: 'qty_diff' },
    { ref: 'ONLY-SYS', doc_qty: null, sys_qty: '7', status: 'missing_in_document' },
  ],
}

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(() => Promise.resolve({})),
}))

vi.mock('./api', () => ({
  api: { get: apiGet, post: apiPost, put: vi.fn(), patch: vi.fn(), del: vi.fn(), upload: vi.fn() },
  downloadFile: vi.fn(),
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))
vi.mock('./i18n', async importOriginal => {
  const actual = await importOriginal<typeof import('./i18n')>()
  return { ...actual, useT: () => (key: string) => key }
})

import { AttachmentSuggestionsPanel, CompareModal, SendDocsPreviewModal } from './DocumentsW5'

describe('AttachmentSuggestionsPanel', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('renders proposed suggestions and accepts with document type', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url === '/api/containers/7/attachment-suggestions') return Promise.resolve([suggestion])
      if (url.startsWith('/api/customs/document-types'))
        return Promise.resolve([{ id: 5, name: 'CMR' }])
      return Promise.reject(new Error(`unexpected ${url}`))
    })
    const onAccepted = vi.fn()
    render(<AttachmentSuggestionsPanel container={container} onAccepted={onAccepted} />)
    await screen.findByText(/cipl\.pdf/)
    expect(screen.getByText('docSuggestions')).toBeTruthy()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '5' } })
    fireEvent.click(screen.getByText('sgAccept'))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/attachment-suggestions/1/accept', { document_type_id: 5 }))
    await waitFor(() => expect(onAccepted).toHaveBeenCalled())
  })

  it('renders nothing when there are no proposed suggestions', async () => {
    apiGet.mockResolvedValue([])
    const { container: dom } = render(<AttachmentSuggestionsPanel container={container} />)
    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    expect(dom.querySelector('.panel')).toBeNull()
  })
})

describe('CompareModal', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('shows invoice vs order report with exceeded flag and mismatch rows', async () => {
    apiGet.mockImplementation((url: string) =>
      url === '/api/invoice-jobs/11/order-compare'
        ? Promise.resolve(report) : Promise.reject(new Error(`unexpected ${url}`)))
    const job = { id: 11, filename: 'cipl.pdf', doc_kind: 'invoice' } as InvoiceJob
    render(<CompareModal job={job} onClose={() => {}} />)
    await screen.findByText('cmpExceeded')
    expect(screen.getByText('NL753-S-40')).toBeTruthy()
    expect(screen.getByText('cmp_qty_diff')).toBeTruthy()
    expect(screen.getByText('cmp_missing_in_document')).toBeTruthy()
  })

  it('uses packing-compare endpoint for packing lists', async () => {
    apiGet.mockResolvedValue({ ...report, kind: 'packing_list', exceeded: undefined })
    const job = { id: 12, filename: 'pl.pdf', doc_kind: 'packing_list' } as InvoiceJob
    render(<CompareModal job={job} onClose={() => {}} />)
    await screen.findByText('NL753-S-40')
    expect(apiGet).toHaveBeenCalledWith('/api/invoice-jobs/12/packing-compare')
  })
})

describe('SendDocsPreviewModal', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('renders rendered template and confirms send', async () => {
    apiGet.mockResolvedValue({ subject: 'Odprawa CMAU8963315', body: 'Dokumenty: cmr.pdf',
      missing: ['Faktura celna'], attachments: 1 })
    const onConfirm = vi.fn()
    render(<SendDocsPreviewModal containerId={7} busy={false}
                                 onConfirm={onConfirm} onClose={() => {}} />)
    await screen.findByText(/Odprawa CMAU8963315/)
    expect(screen.getByText(/cmr\.pdf/)).toBeTruthy()
    expect(screen.getByText('Faktura celna')).toBeTruthy()
    fireEvent.click(screen.getByText('sendAnyway'))   // braki → przycisk „wyślij mimo to”
    expect(onConfirm).toHaveBeenCalled()
  })
})
