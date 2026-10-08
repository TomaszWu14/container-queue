// @vitest-environment jsdom
// audyt UI S3: potwierdzenia w oknie aplikacji zamiast window.confirm/prompt
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (k: string) => k }))

import { ConfirmProvider, useConfirm } from './ConfirmDialog'
import { Modal } from './Modal'

afterEach(cleanup)

function Harness({ onAnswer, danger, ask = 'confirm' }: {
  onAnswer: (v: unknown) => void; danger?: boolean; ask?: 'confirm' | 'prompt'
}) {
  const { confirm, prompt } = useConfirm()
  return <button onClick={async () => onAnswer(ask === 'prompt' ? await prompt('Nazwa?') : await confirm('Usunąć?', { danger }))}>go</button>
}

describe('ConfirmDialog', () => {
  it('Potwierdź → true, okno znika, window.confirm nieużywany', async () => {
    const native = vi.spyOn(window, 'confirm')
    const onAnswer = vi.fn()
    render(<ConfirmProvider><Harness onAnswer={onAnswer} /></ConfirmProvider>)
    fireEvent.click(screen.getByText('go'))
    expect(await screen.findByText('Usunąć?')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'confirm' }))
    await waitFor(() => expect(onAnswer).toHaveBeenCalledWith(true))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(native).not.toHaveBeenCalled()
    native.mockRestore()
  })

  it('Anuluj i Esc → false; danger = fokus na Anuluj i czerwony przycisk', async () => {
    const onAnswer = vi.fn()
    render(<ConfirmProvider><Harness onAnswer={onAnswer} danger /></ConfirmProvider>)
    fireEvent.click(screen.getByText('go'))
    await screen.findByRole('dialog')
    expect(document.activeElement?.textContent).toBe('cancel')
    expect(screen.getByRole('button', { name: 'confirm' }).className).toContain('danger-solid')
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(onAnswer).toHaveBeenCalledWith(false))
  })

  it('prompt zwraca wpisany tekst, Anuluj → null', async () => {
    const onAnswer = vi.fn()
    render(<ConfirmProvider><Harness onAnswer={onAnswer} ask="prompt" /></ConfirmProvider>)
    fireEvent.click(screen.getByText('go'))
    fireEvent.change(await screen.findByLabelText('Nazwa?'), { target: { value: 'Mój widok' } })
    fireEvent.click(screen.getByRole('button', { name: 'confirm' }))
    await waitFor(() => expect(onAnswer).toHaveBeenCalledWith('Mój widok'))
    fireEvent.click(screen.getByText('go'))
    fireEvent.click(await screen.findByRole('button', { name: 'cancel' }))
    await waitFor(() => expect(onAnswer).toHaveBeenLastCalledWith(null))
  })

  it('Esc nad otwartym modalem zamyka tylko potwierdzenie', async () => {
    const onClose = vi.fn(), onAnswer = vi.fn()
    render(<ConfirmProvider><Modal title="Form" onClose={onClose}><Harness onAnswer={onAnswer} /></Modal></ConfirmProvider>)
    fireEvent.click(screen.getByText('go'))
    await screen.findByText('Usunąć?')
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(onAnswer).toHaveBeenCalledWith(false))
    expect(onClose).not.toHaveBeenCalled()
  })
})

// strażnik: natywne okna tylko jako fallback w ConfirmDialog.tsx
const sources = import.meta.glob(['./**/*.ts', './**/*.tsx', '!./**/*.test.*'],
  { query: '?raw', import: 'default', eager: true }) as Record<string, string>

describe('ConfirmDialog — jedno miejsce prawdy', () => {
  it('window.confirm/prompt nie występują poza ConfirmDialog.tsx', () => {
    const offenders = Object.entries(sources)
      .filter(([path, src]) => path !== './ConfirmDialog.tsx' && /window\.(confirm|prompt)\(/.test(src))
      .map(([path]) => path)
    expect(offenders).toEqual([])
  })
})
