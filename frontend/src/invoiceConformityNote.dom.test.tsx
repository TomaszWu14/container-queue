// @vitest-environment jsdom
// Bramka zgodności dokumentu z kontenerem (spec 2026-10-01): sprzeczna / niepewna / PO do przypięcia
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { type Conformity, InvoiceConformityNote } from './InvoiceConformityNote'

vi.mock('./i18n', async importOriginal => {
  const actual = await importOriginal<typeof import('./i18n')>()
  return { ...actual, useT: () => (key: string) => key }
})

const base: Conformity = {
  status: 'ok', overage: false, to_link: [], move_to: [], ack: null,
  signals: [{ key: 'container', ok: true, detail: 'MSDU0806613' }],
}

describe('InvoiceConformityNote', () => {
  afterEach(cleanup)

  it('conflict names the bad signal and the matching container, and moves there', () => {
    const onMove = vi.fn()
    render(<InvoiceConformityNote reason="" onReason={vi.fn()} onLink={vi.fn()} onMove={onMove} conformity={{
      ...base, status: 'conflict', move_to: [{ id: 2, container_no: 'CSQU3054383' }],
      signals: [{ key: 'container', ok: false, detail: 'CSQU3054383' }],
    }} />)
    expect(screen.getByRole('alert').textContent).toContain('confSig_container: CSQU3054383')
    expect(screen.getByRole('alert').textContent).toContain('confFitsTo CSQU3054383')
    fireEvent.click(screen.getByText(/confMoveTo/))
    expect(onMove).toHaveBeenCalledWith(2)
  })

  it('uncertain without ack asks for a reason; PO to link has a button', () => {
    const onReason = vi.fn()
    const onLink = vi.fn()
    render(<InvoiceConformityNote reason="" onReason={onReason} onLink={onLink} conformity={{
      ...base, status: 'uncertain', to_link: ['4500000001'],
      signals: [{ key: 'orders', ok: null, detail: '4500000001' }],
    }} />)
    fireEvent.change(screen.getByLabelText('confReason'), { target: { value: 'brak PO' } })
    expect(onReason).toHaveBeenCalledWith('brak PO')
    fireEvent.click(screen.getByText('invLinkOrders'))
    expect(onLink).toHaveBeenCalled()
  })

  it('acknowledged uncertain shows the reason instead of the input', () => {
    render(<InvoiceConformityNote reason="" onReason={vi.fn()} onLink={vi.fn()} conformity={{
      ...base, status: 'uncertain', ack: { reason: 'skan', by: 'admin', at: '2026-10-01' },
      signals: [{ key: 'container', ok: null, detail: '' }],
    }} />)
    expect(screen.queryByLabelText('confReason')).toBeNull()
    expect(screen.getByText(/skan/)).toBeTruthy()
  })

  it('invoice for several containers offers copy, or marks an existing copy', () => {
    const onCopy = vi.fn()
    render(<InvoiceConformityNote reason="" onReason={vi.fn()} onLink={vi.fn()} onCopy={onCopy} conformity={{
      ...base, also_in: [{ id: 3, container_no: 'CSQU3054383', has_copy: false },
                         { id: 4, container_no: 'TGHU1234567', has_copy: true }],
    }} />)
    fireEvent.click(screen.getByText(/confCopyTo/))
    expect(onCopy).toHaveBeenCalledWith(3)
    expect(screen.getByText('TGHU1234567 ✓')).toBeTruthy()
  })
})
