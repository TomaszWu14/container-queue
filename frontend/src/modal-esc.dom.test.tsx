// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (k: string) => k }))
vi.mock('./api', () => ({ api: {}, errorMessage: (e: unknown) => String(e) }))

import { Modal } from './components'

afterEach(cleanup)

describe('Modal — Esc zamyka (konwencja suity)', () => {
  it('Escape wywołuje onClose', () => {
    const onClose = vi.fn()
    render(<Modal title="Test" onClose={onClose}><p>x</p></Modal>)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
  it('ma role=dialog + aria-modal', () => {
    const { container } = render(<Modal title="T" onClose={() => {}}><p>x</p></Modal>)
    const dialog = container.querySelector('[role="dialog"]')
    expect(dialog?.getAttribute('aria-modal')).toBe('true')
  })
  it('busy blokuje Esc i klik w tło; width/className trafiają na okno', () => {
    const onClose = vi.fn()
    const { container, rerender } = render(
      <Modal title="T" onClose={onClose} busy width={440} className="move-confirm"><p>x</p></Modal>)
    const dialog = container.querySelector('[role="dialog"]') as HTMLElement
    expect(dialog.className).toBe('modal move-confirm')
    expect(dialog.style.maxWidth).toBe('440px')
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(container.querySelector('.modal-backdrop')!)
    expect(onClose).not.toHaveBeenCalled()
    rerender(<Modal title="T" onClose={onClose}><p>x</p></Modal>)
    fireEvent.click(dialog)                 // klik w treść nie zamyka
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(container.querySelector('.modal-backdrop')!)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

// audyt UI S2: pułapka fokusu, fokus startowy, powrót fokusu, X
describe('Modal — fokus i zamknięcie', () => {
  it('fokus wchodzi do okna i wraca na przycisk otwierający po zamknięciu', () => {
    const opener = document.createElement('button')
    document.body.appendChild(opener); opener.focus()
    const { container, unmount } = render(<Modal title="T" onClose={() => {}}><input aria-label="a" /></Modal>)
    expect(container.querySelector('.modal')!.contains(document.activeElement)).toBe(true)
    unmount()
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })
  it('Tab z ostatniego elementu wraca na pierwszy, Shift+Tab z pierwszego na ostatni', () => {
    const { getByLabelText } = render(
      <Modal title="T" onClose={() => {}}><input aria-label="a" /><button>ok</button></Modal>)
    const close = getByLabelText('close'), ok = getByLabelText('a').nextElementSibling as HTMLElement
    ok.focus()
    fireEvent.keyDown(ok, { key: 'Tab' })
    expect(document.activeElement).toBe(close)
    fireEvent.keyDown(close, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(ok)
  })
  it('X zamyka, a w trakcie zapisu (busy) jest zablokowany', () => {
    const onClose = vi.fn()
    const { getByLabelText, rerender } = render(<Modal title="T" onClose={onClose}><p>x</p></Modal>)
    fireEvent.click(getByLabelText('close'))
    expect(onClose).toHaveBeenCalledTimes(1)
    rerender(<Modal title="T" onClose={onClose} busy><p>x</p></Modal>)
    expect((getByLabelText('close') as HTMLButtonElement).disabled).toBe(true)
  })
})

// Strażnik duplikatów: backdrop składa tylko <Modal> — ręczne kopie gubiły Esc i role=dialog.
const sources = import.meta.glob(['./**/*.tsx', '!./**/*.test.tsx'],
  { query: '?raw', import: 'default', eager: true }) as Record<string, string>

describe('Modal — jedno miejsce prawdy', () => {
  it('modal-backdrop występuje tylko w Modal.tsx', () => {
    const offenders = Object.entries(sources)
      .filter(([path, src]) => path !== './Modal.tsx' && src.includes('modal-backdrop'))
      .map(([path]) => path)
    expect(Object.keys(sources).length).toBeGreaterThan(20)
    expect(offenders).toEqual([])
  })
})
