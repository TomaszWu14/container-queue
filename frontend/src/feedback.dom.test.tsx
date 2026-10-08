// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Inbox } from 'lucide-react'
import { EmptyState, LoadError, Skeleton, ToastProvider, useToast } from './feedback'
import ComplaintsPage from './pages/ComplaintsPage'
import { readAppCss } from './appCss.testutil'

vi.mock('./i18n', () => ({ useT: () => (key: string) => ({ retry: 'Spróbuj ponownie' } as Record<string, string>)[key] ?? key }))

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('./api', () => ({
  api: { get: apiGet },
  errorMessage: (e: unknown) => String(e),
}))

afterEach(() => { cleanup(); apiGet.mockReset() })

function ToastTrigger() {
  const { showToast } = useToast()
  return <button onClick={() => showToast('Zapisano')}>trigger</button>
}

describe('feedback — toasty', () => {
  it('toast pojawia się po wywołaniu i znika po czasie (fake timers)', async () => {
    vi.useFakeTimers()
    try {
      render(<ToastProvider><ToastTrigger /></ToastProvider>)
      fireEvent.click(screen.getByText('trigger'))
      expect(screen.getByText('Zapisano')).toBeTruthy()
      await act(async () => { await vi.advanceTimersByTimeAsync(4000) })
      expect(screen.queryByText('Zapisano')).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })

  it('toast ma rolę przycisku i zamyka się klawiaturą (Enter/Escape)', () => {
    render(<ToastProvider><ToastTrigger /></ToastProvider>)
    fireEvent.click(screen.getByText('trigger'))
    const toast = screen.getByText('Zapisano')
    expect(toast.getAttribute('role')).toBe('button')
    expect(toast.getAttribute('tabindex')).toBe('0')
    fireEvent.keyDown(toast, { key: 'Escape' })
    expect(screen.queryByText('Zapisano')).toBeNull()
  })
})

describe('feedback — LoadError', () => {
  it('woła onRetry po kliknięciu', () => {
    const onRetry = vi.fn()
    render(<LoadError message="Błąd" onRetry={onRetry} />)
    screen.getByText('Spróbuj ponownie').click()
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})

describe('feedback — Skeleton', () => {
  it('renderuje n pasków', () => {
    const { container } = render(<Skeleton rows={5} />)
    expect(container.querySelectorAll('.skeleton-row').length).toBe(5)
  })
})

describe('feedback — strażnik CSS', () => {
  it('style aplikacji (src/styles) zawiera klasy .toast i .skeleton', () => {
    const css = readAppCss()
    expect(css).toContain('.toast')
    expect(css).toContain('.skeleton')
  })
})

// Task 4 — rollout: 1 reprezentatywny przypadek spośród dołączonych stron (ComplaintsPage),
// żeby nie duplikować tego samego scenariusza dla każdego zrolloutowanego widoku z osobna.
describe('feedback — rollout na ComplaintsPage', () => {
  it('skeleton przy ładowaniu, LoadError z retry po błędzie API', async () => {
    apiGet.mockImplementationOnce(() => Promise.reject(new Error('boom')))
    apiGet.mockImplementationOnce(() => Promise.resolve([]))
    render(<MemoryRouter><ComplaintsPage /></MemoryRouter>)

    expect(document.querySelector('.skeleton')).toBeTruthy()
    const retryBtn = await screen.findByText('Spróbuj ponownie')
    expect(retryBtn).toBeTruthy()

    fireEvent.click(retryBtn)
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2))
  })
})

// audyt UI PR 4 (C3, B18): jeden błąd = jeden toast; wspólny pusty stan
function ErrorTrigger() {
  const { showToast } = useToast()
  return <button onClick={() => { showToast('Błąd serwera', 'error'); showToast('Błąd serwera', 'error') }}>boom</button>
}

describe('feedback — stany (PR 4)', () => {
  it('ten sam komunikat błędu nie mnoży toastów', () => {
    render(<ToastProvider><ErrorTrigger /></ToastProvider>)
    fireEvent.click(screen.getByText('boom'))
    fireEvent.click(screen.getByText('boom'))
    expect(screen.getAllByText('Błąd serwera')).toHaveLength(1)
  })

  it('błąd widoczny w banerze LoadError nie idzie już toastem', () => {
    render(<ToastProvider><LoadError message="Błąd serwera" /><ErrorTrigger /></ToastProvider>)
    fireEvent.click(screen.getByText('boom'))
    expect(screen.getAllByText('Błąd serwera')).toHaveLength(1)
    expect(document.querySelector('.toast')).toBeNull()
  })

  it('LoadError jest ogłaszany czytnikom (role=alert)', () => {
    render(<LoadError message="Nie udało się" onRetry={() => {}} />)
    expect(screen.getByRole('alert').textContent).toContain('Nie udało się')
  })

  it('EmptyState: tytuł, podpowiedź i akcje', () => {
    render(<EmptyState icon={Inbox} title="Pusto" hint="Zmień filtry"><button>Dodaj</button></EmptyState>)
    expect(screen.getByText('Pusto')).toBeTruthy()
    expect(screen.getByText('Zmień filtry')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Dodaj' })).toBeTruthy()
  })
})
