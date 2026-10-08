// @vitest-environment jsdom
// „Wyślij dokumenty do agencji”: podgląd mówi, że to powiadomienie w aplikacji, komu i jakie pliki;
// bez kont agencji przycisk zablokowany; „mimo braków” = force z podglądu serwera.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (k: string) => k }))
const get = vi.fn()
vi.mock('./api', () => ({ api: { get: (p: string) => get(p) }, downloadFile: vi.fn(), errorMessage: (e: unknown) => String(e) }))

import { SendDocsPreviewModal } from './DocumentsW5'

const base = { subject: 'Dokumenty do odprawy', body: 'treść', attachments: 2, agency: 'Delta',
  files: [{ name: 'BL.pdf', type: 'Konosament' }, { name: 'CI.pdf', type: null }] }

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('SendDocsPreviewModal', () => {
  it('odbiorcy + pliki; braki → wyślij mimo z force=true', async () => {
    get.mockResolvedValue({ ...base, missing: ['SAD'], recipients: ['Anna Celna'] })
    const onConfirm = vi.fn()
    render(<SendDocsPreviewModal containerId={5} busy={false} onConfirm={onConfirm} onClose={() => {}} />)
    expect(await screen.findByText(/Delta — Anna Celna/)).toBeTruthy()
    expect(screen.getByText('BL.pdf')).toBeTruthy()
    expect(screen.getByText('sendDocsInAppHint')).toBeTruthy()
    fireEvent.click(screen.getByText('sendAnyway'))
    expect(onConfirm).toHaveBeenCalledWith(true)
  })

  it('agencja bez kont: zamiast powiadomienia — mail z najnowszej paczki z aktualnym Excelem', async () => {
    const batches = [{ id: 3, attachment_id: 30, excel_current: true }, { id: 4, attachment_id: 40, excel_current: false },
                     { id: 2, attachment_id: 20, excel_current: true }]
    get.mockImplementation((p: string) => Promise.resolve(p.endsWith('/invoice-batches') ? batches
      : p.includes('agency-mail') ? { to: [], cc: [], subject: 's', body: '', agency: 'Delta', warnings: [], attachments: [] }
      : { ...base, missing: [], recipients: [] }))
    render(<SendDocsPreviewModal containerId={5} containerNo="MSKU1" busy={false} onConfirm={() => {}} onClose={() => {}} />)
    expect(await screen.findByText('sendDocsNoRecipients')).toBeTruthy()
    expect(screen.queryByText('sendDocsToAgency')).toBeNull()
    const mail = screen.getByText('invAgencyMail') as HTMLButtonElement
    await waitFor(() => expect(mail.disabled).toBe(false))
    fireEvent.click(mail)
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/invoice-batches/3/agency-mail/preview'))
  })

  it('agencja bez kont i bez aktualnego Excela: wskazówka, mail zablokowany', async () => {
    get.mockImplementation((p: string) => Promise.resolve(p.endsWith('/invoice-batches') ? []
      : { ...base, missing: [], recipients: [] }))
    render(<SendDocsPreviewModal containerId={5} busy={false} onConfirm={() => {}} onClose={() => {}} />)
    expect(await screen.findByText('sendDocsNeedExcel')).toBeTruthy()
    expect((screen.getByText('invAgencyMail') as HTMLButtonElement).disabled).toBe(true)
  })
})
