// @vitest-environment jsdom
// ARCH-004: faktury przetwarzane w tle — dopóki dokument jest „uploaded”, panel sam odpytuje
// paczki; po zakończeniu (extracted/error) odpytywanie staje.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import type { Container, InvoiceBatch } from './types'

const container = { id: 7, container_no: 'CMAU8963315' } as unknown as Container
const job = {
  id: 11, batch_id: 3, filename: 'cipl.pdf', doc_kind: 'invoice', status: 'uploaded', error: '',
  invoice_number: '', container_no: '', delivery_terms: '', page_from: 1, page_to: 2,
  ocr_used: false, items_count: 0, updated_at: '2026-09-28T10:00:00',
} as const
const batch = (status: 'uploaded' | 'extracted'): InvoiceBatch => ({
  id: 3, container_id: 7, supplier_id: null, supplier_name: null, total: 1, confirmed: 0,
  errors: 0, ready: false, excel_current: false, attachment_id: null, attachment_filename: null,
  created_at: '2026-09-28T10:00:00', updated_at: '2026-09-28T10:00:00',
  jobs: [{ ...job, status }],
}) as InvoiceBatch

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('./api', () => ({
  api: { get: apiGet, put: vi.fn(), post: vi.fn(), del: vi.fn(), upload: vi.fn() },
  downloadFile: vi.fn(),
  errorMessage: (e: unknown) => String(e),
}))
vi.mock('./i18n', async importOriginal => {
  const actual = await importOriginal<typeof import('./i18n')>()
  return { ...actual, useT: () => (key: string) => key }
})
vi.mock('./dates', () => ({ formatDateTime: (s: string) => s, parseServerTs: (s: string) => new Date(`${s}Z`) }))

import { INGEST_POLL_MS, InvoiceBatchesPanel } from './InvoiceBatchesPanel'

const batchCalls = () =>
  apiGet.mock.calls.filter(([url]) => url === '/api/containers/7/invoice-batches').length

describe('InvoiceBatchesPanel — przetwarzanie w tle', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); vi.useRealTimers() })

  it('odpytuje paczki, dopóki dokument jest w kolejce, potem przestaje', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const responses = [[batch('uploaded')], [batch('uploaded')], [batch('extracted')]]
    apiGet.mockImplementation((url: string) => url === '/api/containers/7/invoice-batches'
      ? Promise.resolve(responses.shift() ?? [batch('extracted')])
      : Promise.resolve([]))
    render(<InvoiceBatchesPanel container={container} />)
    await screen.findByText('invStatus_uploaded')
    expect(screen.getByRole('status').textContent).toBe('invProcessingInBackground')
    expect(batchCalls()).toBe(1)

    await vi.advanceTimersByTimeAsync(INGEST_POLL_MS + 100)
    await waitFor(() => expect(batchCalls()).toBe(2))
    await vi.advanceTimersByTimeAsync(INGEST_POLL_MS + 100)
    await waitFor(() => expect(batchCalls()).toBe(3))
    await screen.findByText('invStatus_extracted')
    expect(screen.queryByRole('status')).toBeNull()

    await vi.advanceTimersByTimeAsync(INGEST_POLL_MS * 3)
    expect(batchCalls()).toBe(3)          // po zakończeniu bez dalszego odpytywania
  })

  it('bez dokumentów w kolejce nie odpytuje', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    apiGet.mockImplementation((url: string) => Promise.resolve(
      url === '/api/containers/7/invoice-batches' ? [batch('extracted')] : []))
    render(<InvoiceBatchesPanel container={container} />)
    await screen.findByText('invStatus_extracted')
    await vi.advanceTimersByTimeAsync(INGEST_POLL_MS * 2)
    expect(batchCalls()).toBe(1)
  })

  it('zestaw w kolejce: „w kolejce” / „przetwarzanie od N min” zamiast „0 pozycji”, bez „Pomiń”', async () => {
    const started = new Date(Date.now() - 12 * 60000).toISOString().slice(0, 19)
    apiGet.mockImplementation((url: string) => url === '/api/containers/7/invoice-batches'
      ? Promise.resolve([{ ...batch('uploaded'), jobs: [{ ...job, processing_started_at: started }] }])
      : Promise.resolve([]))
    render(<InvoiceBatchesPanel container={container} />)
    expect(await screen.findByText(/invProcessingSince/)).toBeTruthy()
    expect(screen.queryByText(/refRows/)).toBeNull()
    expect(screen.queryByText('invIgnore')).toBeNull()
  })
})
