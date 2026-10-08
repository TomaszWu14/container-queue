// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { Field } from './Field'

afterEach(cleanup)

describe('Field', () => {
  it('etykieta nazywa pole, podpowiedź i błąd są podpięte przez aria-describedby', () => {
    render(<Field label="E-mail" hint="służbowy" error="Nieprawidłowy adres"><input /></Field>)
    const input = screen.getByLabelText(/E-mail/)
    const ids = (input.getAttribute('aria-describedby') ?? '').split(' ')
    expect(ids.map(id => document.getElementById(id)?.textContent)).toEqual(['służbowy', 'Nieprawidłowy adres'])
    expect(input.getAttribute('aria-invalid')).toBe('true')
    expect(screen.getByRole('alert').textContent).toBe('Nieprawidłowy adres')
  })

  it('bez błędu i podpowiedzi — bez aria-describedby/aria-invalid', () => {
    render(<Field label="Nazwa"><input /></Field>)
    const input = screen.getByLabelText('Nazwa')
    expect(input.hasAttribute('aria-describedby')).toBe(false)
    expect(input.hasAttribute('aria-invalid')).toBe(false)
  })
})
