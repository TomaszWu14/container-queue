// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ErrorBoundary } from './ErrorBoundary'

afterEach(cleanup)

function Boom(): never { throw new Error('boom') }

describe('ErrorBoundary', () => {
  it('pokazuje fallback zamiast białego ekranu gdy dziecko rzuca', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})  // wycisz log Reacta
    render(<ErrorBoundary fallback={<span>Coś poszło nie tak</span>}><Boom /></ErrorBoundary>)
    expect(screen.getByText('Coś poszło nie tak')).toBeTruthy()
    spy.mockRestore()
  })

  it('renderuje dzieci gdy nie ma błędu', () => {
    render(<ErrorBoundary fallback={<span>fallback</span>}><span>ok</span></ErrorBoundary>)
    expect(screen.getByText('ok')).toBeTruthy()
    expect(screen.queryByText('fallback')).toBeNull()
  })

  it('regresja: po błędzie jednej strony nowy resetKey (ścieżka) zdejmuje fallback', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { rerender } = render(
      <ErrorBoundary resetKey="/zla" fallback={<span>fallback</span>}><Boom /></ErrorBoundary>)
    expect(screen.getByText('fallback')).toBeTruthy()
    rerender(<ErrorBoundary resetKey="/dobra" fallback={<span>fallback</span>}><span>ok</span></ErrorBoundary>)
    expect(screen.getByText('ok')).toBeTruthy()
    spy.mockRestore()
  })
})
