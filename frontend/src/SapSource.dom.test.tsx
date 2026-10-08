// @vitest-environment jsdom
// Strażnik (2026-09-29): przy imporcie z SAP plakietka tabeli SE16N + ⓘ z opisem.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (key: string) => key }))

import { SapSource } from './SapSource'

afterEach(cleanup)

describe('SapSource', () => {
  it('plakietka z tabelą i dymek z opisem po kliknięciu ⓘ', () => {
    render(<SapSource table="EKKO" />)
    expect(screen.getByText('EKKO').className).toBe('sap-tag')
    fireEvent.click(screen.getByRole('button', { name: 'se16nSource: EKKO' }))
    expect(screen.getByRole('tooltip').textContent).toBe('se16n_EKKO')
  })
})
