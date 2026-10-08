// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OrdersPage from './OrdersPage'

vi.mock('../i18n', () => ({ useT: () => (key: string) => ({ retry: 'Spróbuj ponownie' } as Record<string, string>)[key] ?? key }))

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api', () => ({ api: { get: apiGet }, errorMessage: (e: unknown) => String(e) }))

afterEach(() => { cleanup(); apiGet.mockReset() })

// Task 4 — rollout: przypadek OrdersPage (lista z debounce) — skeleton przy pierwszym
// ładowaniu, LoadError z retry po błędzie API.
describe('feedback — rollout na OrdersPage', () => {
  it('skeleton przy ładowaniu, LoadError z retry po błędzie API', async () => {
    apiGet.mockImplementationOnce(() => Promise.reject(new Error('boom')))
    apiGet.mockImplementationOnce(() => Promise.resolve([]))
    render(<MemoryRouter><OrdersPage /></MemoryRouter>)

    expect(document.querySelector('.skeleton')).toBeTruthy()
    const retryBtn = await screen.findByText('Spróbuj ponownie')
    expect(retryBtn).toBeTruthy()

    fireEvent.click(retryBtn)
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2))
  })
})
