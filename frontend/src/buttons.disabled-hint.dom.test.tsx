// @vitest-environment jsdom
// A31 (audyt UI): nieaktywny przycisk zapisu mówi, czego brakuje; po uzupełnieniu podpowiedź znika
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MessagesPanel } from './collaboration'
import type { Container } from './types'

vi.mock('./api', () => ({ api: { get: vi.fn(() => Promise.resolve([])), post: vi.fn() }, errorMessage: String }))
vi.mock('./App', () => ({ useUser: () => ({ role: 'logistics', id: 1 }) }))
afterEach(cleanup)

it('„Wyślij”: nieaktywny z podpowiedzią, po wpisaniu treści aktywny', async () => {
  render(<MessagesPanel container={{ id: 5 } as Container} />)
  const send = await screen.findByRole('button', { name: 'Wyślij' }) as HTMLButtonElement
  expect(send.disabled).toBe(true)
  expect(send.title).toBe('Wpisz treść wiadomości')
  fireEvent.change(screen.getByRole('textbox', { name: 'Napisz wiadomość…' }), { target: { value: 'Hej' } })
  expect(send.disabled).toBe(false)
  expect(send.title).toBe('')
})
