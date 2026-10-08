// @vitest-environment jsdom
// Szuflada → Dokumenty: części zestawów z paczek faktur widoczne (audyt #20), bez zaślepek w kolejce;
// rola bez dostępu do faktur (403) — sekcji nie ma.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (k: string) => k }))
const get = vi.fn()
const download = vi.fn().mockResolvedValue(undefined)
vi.mock('../../api', () => ({
  api: { get: (p: string) => get(p) },
  downloadFile: (u: string, n: string) => download(u, n), errorMessage: (e: unknown) => String(e),
}))

import { BatchDocuments } from './BatchDocuments'

const job = (id: number, filename: string, doc_kind: string, status: string) =>
  ({ id, filename, doc_kind, status, invoice_number: '' })

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('BatchDocuments', () => {
  it('lista części (bez zaślepek w kolejce) i podgląd PDF części', async () => {
    get.mockResolvedValue([{ id: 1, jobs: [job(5, 'DOC_BL_s1.pdf', 'other', 'ignored'),
      job(6, 'DOC_faktura_s2.pdf', 'invoice', 'extracted'), job(7, 'NOWY.pdf', 'invoice', 'uploaded')] }])
    render(<BatchDocuments containerId={9} />)
    expect(await screen.findByText('DOC_BL_s1.pdf')).toBeTruthy()
    expect(screen.queryByText('NOWY.pdf')).toBeNull()
    fireEvent.click(screen.getAllByText('mailPrevOpen')[0])
    expect(download).toHaveBeenCalledWith('/api/invoice-jobs/5/pdf', 'DOC_BL_s1.pdf')
  })

  it('403 (rola bez faktur) — nic nie renderuje', async () => {
    get.mockRejectedValue(new Error('403'))
    const { container } = render(<BatchDocuments containerId={9} />)
    await new Promise(r => setTimeout(r, 0))
    expect(container.innerHTML).toBe('')
  })
})
