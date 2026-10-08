// @vitest-environment jsdom
// Strażnik: na HTTP (serwer bez TLS) navigator.clipboard nie istnieje — kopiowanie
// ma zejść do execCommand, a nie cicho nic nie zrobić (błąd z testów 2026-09-24).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'

const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }))
vi.mock('./i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('./feedback', () => ({ useToast: () => ({ showToast }) }))

import { CopyButton, copyToClipboard } from './clipboard'

afterEach(() => { cleanup(); showToast.mockClear(); vi.useRealTimers() })

const execCommand = vi.fn(() => true)
Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true })

describe('copyToClipboard', () => {
  it('bez bezpiecznego kontekstu używa ukrytego textarea + execCommand', async () => {
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true })
    await copyToClipboard('TRHU0003565')
    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(document.querySelector('textarea')).toBeNull()   // sprząta po sobie
  })

  it('odrzuca, gdy przeglądarka odmówi kopiowania', async () => {
    execCommand.mockReturnValueOnce(false)
    await expect(copyToClipboard('x')).rejects.toThrow()
  })
})

describe('CopyButton', () => {
  it('✓ na 1,5 s + toast, klik nie dochodzi do wiersza', async () => {
    vi.useFakeTimers()
    const rowClick = vi.fn()
    render(<div onClick={rowClick}><CopyButton text="4500617421" /></div>)
    const btn = screen.getByRole('button')
    expect(btn.getAttribute('data-copy')).toBe('4500617421')
    await act(async () => { fireEvent.click(btn) })
    expect(btn.textContent).toBe('✓')
    expect(showToast).toHaveBeenCalledWith('copied', 'success')
    expect(rowClick).not.toHaveBeenCalled()
    act(() => { vi.advanceTimersByTime(1600) })
    expect(btn.textContent).toBe('⧉')
  })

  it('błąd kopiowania = toast z błędem', async () => {
    execCommand.mockReturnValueOnce(false)
    render(<CopyButton text="x" />)
    await act(async () => { fireEvent.click(screen.getByRole('button')) })
    expect(showToast).toHaveBeenCalledWith('copyFailed', 'error')
  })
})
