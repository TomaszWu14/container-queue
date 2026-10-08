// @vitest-environment jsdom
// Strażnik (2026-09-29, spec agencja-draft-sad PR 1): potwierdzenie, wersje draftu, decyzja.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (key: string) => key }))
const get = vi.fn(), post = vi.fn(), upload = vi.fn()
vi.mock('./api', () => ({
  api: { get: (p: string) => get(p), post: (p: string, b: unknown) => post(p, b),
         upload: (p: string, f: File) => upload(p, f) },
  downloadFile: vi.fn(), errorMessage: String,
}))
vi.mock('./SadCompareModal', () => ({
  SadCompareModal: ({ draft }: { draft: { version: number } }) => <p>compare v{draft.version}</p> }))

import { AgencySadSection } from './AgencySadSection'

const draft = (version: number, decision = 'pending') => ({
  id: version, version, attachment_id: 10 + version, filename: `SAD_v${version}.pdf`,
  source: 'manual', decision, comment: '', created_at: '2026-09-29T14:05:00',
  decided_at: null, decided_by: null })

afterEach(() => { cleanup(); get.mockReset(); post.mockReset(); upload.mockReset() })

describe('AgencySadSection', () => {
  it('bez potwierdzenia: przycisk potwierdza odbiór', async () => {
    get.mockResolvedValue({ ack: null, drafts: [] })
    post.mockResolvedValue({ ack: { at: '2026-09-29T14:05:00', source: 'manual', by: 'Anna' }, drafts: [] })
    render(<AgencySadSection batchId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: 'sadAckBtn' }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/invoice-batches/7/agency-ack', {}))
    expect(await screen.findByText(/sadAcked/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'sadAckBtn' })).toBeNull()
  })

  it('decyzja tylko dla najnowszej wersji; „do poprawy” wymaga komentarza', async () => {
    get.mockResolvedValue({ ack: { at: '2026-09-29T14:05:00', source: 'manual', by: null },
                            drafts: [draft(2), draft(1, 'rejected')] })
    post.mockResolvedValue({ ack: null, drafts: [draft(2, 'rejected'), draft(1, 'rejected')] })
    render(<AgencySadSection batchId={7} />)
    expect(await screen.findAllByRole('button', { name: 'sadAccept' })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'sadReject' }))
    const save = screen.getByRole('button', { name: 'sadSend' }) as HTMLButtonElement
    expect(save.disabled).toBe(true)                                  // pusty komentarz
    fireEvent.change(screen.getByLabelText('sadCommentLabel'), { target: { value: 'zły CN' } })
    fireEvent.click(save)
    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/api/invoice-batches/7/sad-drafts/2/decision', { decision: 'rejected', comment: 'zły CN' }))
  })

  it('ten sam plik drugi raz: komunikat „już jest (vN)” zamiast nowej wersji', async () => {
    const state = { ack: null, drafts: [draft(1)] }
    get.mockResolvedValue(state)
    upload.mockResolvedValue({ draft: draft(1), created: false, state })
    render(<AgencySadSection batchId={7} />)
    const input = await screen.findByLabelText('sadUpload')
    fireEvent.change(input, { target: { files: [new File(['%PDF'], 'SAD.pdf', { type: 'application/pdf' })] } })
    await waitFor(() => expect(upload).toHaveBeenCalledWith('/api/invoice-batches/7/sad-drafts', expect.any(File)))
    expect((await screen.findByRole('status')).textContent).toBe('sadDuplicate')
  })

  it('„Porównaj” otwiera okno porównania wybranej wersji', async () => {
    const compared = { ...draft(1, 'rejected'), summary: { groups: 2, ok: 1, diff: 1, manual: 0, all_ok: false } }
    get.mockResolvedValue({ ack: null, drafts: [draft(2), compared] })
    render(<AgencySadSection batchId={7} />)
    expect(await screen.findByText('sadSummaryIssues')).toBeTruthy()   // podsumowanie ostatniego porównania
    fireEvent.click((await screen.findAllByRole('button', { name: 'sadCompare' }))[1])
    expect(await screen.findByText('compare v1')).toBeTruthy()
  })

  it('„+ XML” dołącza XML do tej wersji; znacznik pokazuje źródło danych porównania', async () => {
    const withXml = { ...draft(1), xml_attachment_id: 21, xml_filename: 'SAD7100005.xml', data_from: 'xml' }
    get.mockResolvedValue({ ack: null, drafts: [{ ...draft(1), data_from: 'pdf' }] })
    upload.mockResolvedValue({ created: true, state: { ack: null, drafts: [withXml] } })
    render(<AgencySadSection batchId={7} />)
    expect(await screen.findByText('sadData_pdf')).toBeTruthy()        // wstępnie z PDF
    fireEvent.change(screen.getByLabelText('sadAddXml'),
                     { target: { files: [new File(['<SADUE/>'], 'SAD7100005.xml', { type: 'application/xml' })] } })
    await waitFor(() => expect(upload).toHaveBeenCalledWith('/api/invoice-batches/7/sad-drafts/1/xml', expect.any(File)))
    expect(await screen.findByText('sadData_xml')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'sadShowXml' })).toBeTruthy()
    expect(screen.queryByLabelText('sadAddXml')).toBeNull()           // wersja ma już XML
  })
})
