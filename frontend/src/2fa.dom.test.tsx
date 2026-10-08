// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import LoginPage from './pages/LoginPage'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('Logowanie z 2FA', () => {
  it('totp_required → drugi krok z polem kodu → wysyłka /api/auth/2fa/verify', async () => {
    const calls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      calls.push(url)
      if (url.includes('/api/auth/login'))
        return jsonResponse({ totp_required: true, pending_token: 'PT123' })
      if (url.includes('/api/auth/2fa/verify')) return jsonResponse({ ok: true })
      return jsonResponse({})
    }))
    const onLogin = vi.fn()
    render(<MemoryRouter><LoginPage onLogin={onLogin} /></MemoryRouter>)

    fireEvent.change(screen.getByLabelText('Login'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText('Hasło'), { target: { value: 'sekret123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zaloguj się' }))

    // drugi krok: pole kodu zamiast natychmiastowego onLogin
    const codeInput = await screen.findByLabelText('Kod z aplikacji (lub kod zapasowy)')
    expect(onLogin).not.toHaveBeenCalled()

    fireEvent.change(codeInput, { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź kod' }))

    await waitFor(() => expect(onLogin).toHaveBeenCalled())
    expect(calls.some(u => u.includes('/api/auth/2fa/verify'))).toBe(true)
  })

  it('zły kod (401) → komunikat o nieprawidłowym kodzie', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/auth/login'))
        return jsonResponse({ totp_required: true, pending_token: 'PT123' })
      // verify i refresh (401→retry w api.ts) — oba odrzucamy
      return jsonResponse({ detail: 'zły kod' }, 401)
    }))
    render(<MemoryRouter><LoginPage onLogin={vi.fn()} /></MemoryRouter>)

    fireEvent.change(screen.getByLabelText('Login'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText('Hasło'), { target: { value: 'sekret123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zaloguj się' }))

    const codeInput = await screen.findByLabelText('Kod z aplikacji (lub kod zapasowy)')
    fireEvent.change(codeInput, { target: { value: '000000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź kod' }))

    await screen.findByText('Nieprawidłowy kod. Spróbuj ponownie.')
  })
})
