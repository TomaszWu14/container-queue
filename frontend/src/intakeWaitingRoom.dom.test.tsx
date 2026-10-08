// @vitest-environment jsdom
// Poczekalnia — plaster 2 (spec 2026-10-06 §3): „Dodaj dokumenty” → okno „Sprawdź i potwierdź”
// (typ, przeniesienie, odrzucenie, potwierdzenie, 409, odrzucenie całości) i pasek oczekujących.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (k: string) => (k === 'inqWaiting' ? '{n} czeka' : k) }))
let role = 'logistics'
vi.mock('./App', () => ({ useUser: () => ({ role }) }))
const showToast = vi.fn()
vi.mock('./feedback', () => ({ useToast: () => ({ showToast }) }))
const ask = vi.fn()
vi.mock('./ConfirmDialog', () => ({ useConfirm: () => ({ confirm: (...a: unknown[]) => ask(...a) }) }))
const get = vi.fn(), post = vi.fn(), patch = vi.fn(), upload = vi.fn()
vi.mock('./api', () => ({
  api: {
    get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a),
    patch: (...a: unknown[]) => patch(...a), upload: (...a: unknown[]) => upload(...a),
  },
  errorMessage: (e: unknown) => (e as Error).message,
}))

import { IntakePanel } from './IntakeWaitingRoom'
import type { IntakeBatch, IntakeItem } from './IntakeWaitingRoom'

const item = (over: Partial<IntakeItem>): IntakeItem => ({
  id: 1, original_name: 'ci.pdf', page_from: 1, page_to: 2, pages: 2, doc_type: 'CI',
  target_container_id: 7, target_container_no: 'MSKU1', gate_status: 'ok', gate_message: '',
  decision: 'pending', found_containers: [], ...over,
})
const BATCH: IntakeBatch = {
  id: 50, container_id: 7, status: 'pending', items: [
    item({}),
    item({ id: 2, original_name: 'bl.pdf', doc_type: 'BL', gate_status: 'conflict', gate_message: 'BL dla TGHU2',
           found_containers: [{ container_no: 'TGHU2', container_id: 8 }] }),
  ],
}

afterEach(() => { cleanup(); vi.clearAllMocks(); role = 'logistics' })

const mountWithUpload = async (onChanged = vi.fn()) => {
  get.mockResolvedValue([])
  upload.mockResolvedValue(BATCH)
  const { container } = render(<IntakePanel containerId={7} onChanged={onChanged} />)
  const input = container.querySelector('input[type=file]') as HTMLInputElement
  fireEvent.change(input, { target: { files: [new File(['x'], 'all.zip')] } })
  await screen.findByRole('dialog')
  return onChanged
}

describe('IntakePanel / okno „Sprawdź i potwierdź”', () => {
  it('wgranie → okno z częściami, typami i wynikiem bramki', async () => {
    await mountWithUpload()
    expect(upload).toHaveBeenCalledWith('/api/containers/7/intake', [expect.any(File)], 'files')
    expect((screen.getByLabelText('inqType: ci.pdf') as HTMLSelectElement).value).toBe('CI')
    expect(screen.getByText('inqGate_ok')).toBeTruthy()
    expect(screen.getByText('inqGate_conflict')).toBeTruthy()
    expect(screen.getByText('BL dla TGHU2')).toBeTruthy()
  })

  it('zmiana typu, „Przenieś do”, „Odrzuć” → PATCH części', async () => {
    await mountWithUpload()
    patch.mockImplementation((_p: string, body: object) => Promise.resolve(body))
    fireEvent.change(screen.getByLabelText('inqType: ci.pdf'), { target: { value: 'PI' } })
    await waitFor(() => expect(patch).toHaveBeenCalledWith('/api/intake/items/1', { doc_type: 'PI' }))
    fireEvent.click(await screen.findByText('inqMoveTo'))
    await waitFor(() => expect(patch).toHaveBeenCalledWith('/api/intake/items/2', { target_container_id: 8 }))
    await waitFor(() => expect(screen.queryByText('inqMoveTo')).toBeNull())   // już w docelowym
    fireEvent.click(screen.getAllByText('inqReject')[0])
    await waitFor(() => expect(patch).toHaveBeenCalledWith('/api/intake/items/1', { decision: 'rejected' }))
    expect(await screen.findByText('inqRestore')).toBeTruthy()
  })

  it('„Potwierdź” → POST confirm, toast, zamknięcie i odświeżenie rodzica', async () => {
    const onChanged = await mountWithUpload()
    post.mockResolvedValue({ containers: { MSKU1: { invoices: 1, attachments: 0 } }, skipped: [] })
    fireEvent.click(screen.getByText('inqConfirm'))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/intake/50/confirm', {}))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(showToast).toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('409 przy „Potwierdź” → komunikat serwera, okno zostaje', async () => {
    const onChanged = await mountWithUpload()
    post.mockRejectedValue(new Error('Rozstrzygnij części: bl.pdf'))
    fireEvent.click(screen.getByText('inqConfirm'))
    expect((await screen.findByRole('alert')).textContent).toContain('Rozstrzygnij części')
    expect(screen.getByRole('dialog')).toBeTruthy()
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('„Odrzuć całość” pyta, potem POST discard', async () => {
    const onChanged = await mountWithUpload()
    ask.mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    post.mockResolvedValue(undefined)
    fireEvent.click(screen.getByText('inqDiscard'))
    await waitFor(() => expect(ask).toHaveBeenCalledTimes(1))
    expect(post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('inqDiscard'))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/intake/50/discard', {}))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
  })

  it('pasek: liczba czekających części, „Sprawdź” otwiera najstarsze wgranie', async () => {
    get.mockResolvedValue([BATCH, { ...BATCH, id: 51, items: [item({ id: 3 })] }])
    render(<IntakePanel containerId={7} />)
    expect((await screen.findByRole('status')).textContent).toContain('3 czeka')
    expect(get).toHaveBeenCalledWith('/api/containers/7/intake?status=pending')
    fireEvent.click(screen.getByText('inqReview'))
    expect(await screen.findByText('bl.pdf')).toBeTruthy()   // wgranie 50, nie 51
  })

  it.each(['sales', 'warehouse'])('rola %s nie widzi poczekalni', role_ => {
    role = role_
    const { container } = render(<IntakePanel containerId={7} />)
    expect(container.innerHTML).toBe('')
    expect(get).not.toHaveBeenCalled()
  })
})
