// @vitest-environment jsdom
// Strażnik (2026-09-24): Anuluj, Esc i klik w tło przy niezapisanych zmianach pytają
// „porzucić?"; bez zmian zamykają od razu; odmowa zostawia formularz otwarty.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (key: string) => key, LangContext: { Provider: ({ children }: { children: unknown }) => children } }))
vi.mock('./api', () => ({ api: { post: vi.fn() }, errorMessage: String }))

import { StatusModal } from './components'
import type { Container } from './types'

const C = { id: 1, container_no: 'TRHU0003565', status: 'ODPRAWA' } as Container
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const mount = (onClose = vi.fn()) => {
  render(<StatusModal container={C} warehouseRole={false} onSaved={() => {}} onClose={onClose} />)
  return onClose
}

describe('porzucanie niezapisanych zmian', () => {
  it('bez zmian Anuluj zamyka bez pytania', () => {
    const confirm = vi.spyOn(window, 'confirm')
    const onClose = mount()
    fireEvent.click(screen.getByText('cancel'))
    expect(confirm).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('ze zmianą: Esc pyta, odmowa zostawia otwarte, zgoda zamyka', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    const onClose = mount()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'uwaga' } })
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(confirm).toHaveBeenCalledWith('discardChanges')
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(document.querySelector('.modal-backdrop')!)
    // odpowiedź potwierdzenia przychodzi przez Promise (useConfirm)
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('zamknięcie karty: brudny formularz → beforeunload pyta, czysty → nie', () => {
    mount()
    const unload = () => {
      const ev = new Event('beforeunload', { cancelable: true })
      window.dispatchEvent(ev)
      return ev.defaultPrevented
    }
    expect(unload()).toBe(false)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'uwaga' } })
    expect(unload()).toBe(true)
    cleanup()                       // zamknięty formularz nie blokuje już wyjścia
    expect(unload()).toBe(false)
  })
})
