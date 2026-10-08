// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (k: string) => k }))
const answer = { current: true }
const reason = { current: 'korekta' as string | null }
vi.mock('./ConfirmDialog', () => ({ useConfirm: () => ({
  confirm: () => Promise.resolve(answer.current), prompt: () => Promise.resolve(reason.current) }) }))
const calls: string[] = []
vi.mock('./api', () => ({
  api: {
    del: (p: string) => { calls.push(`DEL ${p}`); return Promise.resolve() },
    upload: (p: string, _f: File, _n: string, extra?: Record<string, string>) => {
      calls.push(`UP ${p} ${JSON.stringify(extra ?? {})}`); return Promise.resolve({})
    },
  },
  errorMessage: (e: unknown) => String(e),
}))

import { AttachmentActions, SharedBadge } from './AttachmentActions'
import type { Attachment } from './types'

const att = { id: 9, filename: 'zly.pdf', document_type_id: 4 } as Attachment
const renderIt = (onChanged = vi.fn()) => {
  render(<AttachmentActions attachment={att} containerId={3} busy={false} setBusy={() => {}}
                            onChanged={onChanged} onError={() => {}} linkClass="x" />)
  return onChanged
}

afterEach(() => { cleanup(); calls.length = 0; answer.current = true; reason.current = 'korekta' })

describe('AttachmentActions', () => {
  it('Podmień: jedno żądanie z replaces_id (serwer zachowuje typ i usuwa stary plik)', async () => {
    const onChanged = renderIt()
    const input = screen.getByLabelText('attReplace') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['x'], 'dobry.pdf')] } })
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(calls).toEqual(['UP /api/containers/3/attachments {"replaces_id":"9"}'])
  })

  it('po wysłaniu: powód obowiązkowy, bez Usuń; brak powodu = nic nie wysyła', async () => {
    cleanup()
    const sent = { ...att, can_delete: false, can_replace: true, replace_needs_reason: true } as Attachment
    render(<AttachmentActions attachment={sent} containerId={3} busy={false} setBusy={() => {}}
                              onChanged={() => {}} onError={() => {}} linkClass="x" />)
    expect(screen.queryByText('attDelete')).toBeNull()
    const input = () => screen.getByLabelText('attReplace') as HTMLInputElement
    reason.current = null
    fireEvent.change(input(), { target: { files: [new File(['x'], 'a.pdf')] } })
    await new Promise(r => setTimeout(r, 0))
    expect(calls).toEqual([])
    reason.current = 'korekta wagi'
    fireEvent.change(input(), { target: { files: [new File(['x'], 'a.pdf')] } })
    await waitFor(() => expect(calls).toEqual(['UP /api/containers/3/attachments {"replaces_id":"9","replace_reason":"korekta wagi"}']))
  })

  it('Usuń: tylko po potwierdzeniu', async () => {
    answer.current = false
    renderIt()
    fireEvent.click(screen.getByText('attDelete'))
    await new Promise(r => setTimeout(r, 0))
    expect(calls).toEqual([])
    answer.current = true
    fireEvent.click(screen.getByText('attDelete'))
    await waitFor(() => expect(calls).toEqual(['DEL /api/attachments/9']))
  })

  it('wspólny plik: plakietka „wspólny z X, Y”, w powiązanym tylko Odepnij', async () => {
    const linked = { ...att, shared_with: ['MSCU1', 'CSQU2'], owner_container_no: 'MSCU1',
                     can_delete: false, can_replace: false, can_unlink: true } as Attachment
    render(<><SharedBadge attachment={linked} />
      <AttachmentActions attachment={linked} containerId={3} busy={false} setBusy={() => {}}
                         onChanged={() => {}} onError={() => {}} linkClass="x" /></>)
    expect(screen.getByText('attSharedWith').textContent).toBe('attSharedWith')
    expect(screen.queryByText('attDelete')).toBeNull()
    fireEvent.click(screen.getByText('attUnlink'))
    await waitFor(() => expect(calls).toEqual(['DEL /api/containers/3/attachments/9/link']))
  })

  it('plik bez powiązań: brak plakietki', () => {
    const { container } = render(<SharedBadge attachment={att} />)
    expect(container.innerHTML).toBe('')
  })
})
