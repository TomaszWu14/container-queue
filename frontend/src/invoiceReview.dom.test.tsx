// @vitest-environment jsdom
// Okno weryfikacji faktury (audyt 2026-10-06 #25/#26): oryginał PDF do otwarcia, ostrzeżenie
// o pozycjach bez dopasowania (znika po wpisaniu REF albo pominięciu pozycji).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (k: string) => k }))
const download = vi.fn().mockResolvedValue(undefined)
const item = (id: number, raw: string, match_status: string, master_ref = '') => ({
  id, line_no: id, raw_ref: raw, descr: '', qty: '1', amount: '1', weight_net: '', weight_gross: '',
  master_ref, name_pl: '', tariff_cn: '', match_status, match_source: '', skipped: false,
  ml_suggestion: '', weight_source: '', uom_factor: '', sent: false,
})
const job = { id: 7, filename: 'DOC_faktura_s2.pdf', invoice_number: 'CBN-1', status: 'extracted',
  container_no: '', delivery_terms: '', ocr_used: false,
  items: [item(1, 'NL753', 'matched', 'NL753-S-40'), item(2, 'X9', 'unmatched'), item(3, 'X8', 'unmatched')] }
vi.mock('./api', () => ({
  api: { get: (p: string) => Promise.resolve(p.endsWith('/conformity') ? null : job), put: vi.fn(), post: vi.fn() },
  downloadFile: (u: string, n: string) => download(u, n), errorMessage: (e: unknown) => String(e),
}))

import { InvoiceReviewModal } from './InvoiceReviewModal'

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('InvoiceReviewModal', () => {
  it('otwiera oryginał PDF i ostrzega o pozycjach bez dopasowania', async () => {
    render(<InvoiceReviewModal jobId={7} onClose={() => {}} onSaved={() => {}} />)
    fireEvent.click(await screen.findByText('invOpenPdf'))
    expect(download).toHaveBeenCalledWith('/api/invoice-jobs/7/pdf', 'DOC_faktura_s2.pdf')
    expect(screen.getByRole('status').textContent).toBe('invUnmatchedWarn')
  })
})
