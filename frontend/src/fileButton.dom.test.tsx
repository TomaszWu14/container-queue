// @vitest-environment jsdom
// §4 pkt 48/49: przycisk wgrywania to prawdziwy <button> (Tab/Enter działają); panel plików nie
// ma „Wgraj” (spec 2026-10-06: nowe pliki tylko przez poczekalnię), błąd listy pokazany, nie połknięty
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

const { apiGet, role } = vi.hoisted(() => ({ apiGet: vi.fn(), role: { value: 'sales' } }))
vi.mock('./api', () => ({
  api: { get: apiGet, upload: vi.fn(), post: vi.fn(), del: vi.fn() },
  downloadFile: vi.fn(), errorMessage: (e: unknown) => String(e),
}))
vi.mock('./App', () => ({ useUser: () => ({ role: role.value }) }))

import { FileButton } from './FilePicker'
import { AttachmentsPanel } from './collaboration'
import type { Container } from './types'

afterEach(() => { cleanup(); apiGet.mockReset() })

describe('FileButton', () => {
  it('jest przyciskiem, który otwiera ukryty wybór pliku i oddaje pliki', () => {
    const onFiles = vi.fn()
    render(<FileButton onFiles={onFiles}>Wgraj</FileButton>)
    const button = screen.getByRole('button', { name: 'Wgraj' })
    expect(button.tagName).toBe('BUTTON')
    const input = screen.getByLabelText('Wgraj') as HTMLInputElement
    const click = vi.spyOn(input, 'click')
    fireEvent.click(button)
    expect(click).toHaveBeenCalled()
    fireEvent.change(input, { target: { files: [new File(['x'], 'a.pdf')] } })
    expect(onFiles).toHaveBeenCalledWith([expect.any(File)])
  })
})

describe('AttachmentsPanel — bez wgrywania', () => {
  it.each(['sales', 'logistics'])('%s: bez „Wgraj”; błąd listy plików widoczny', async r => {
    role.value = r
    apiGet.mockImplementation((path: string) => path.includes('/attachments')
      ? Promise.reject(new Error('Brak połączenia')) : Promise.resolve([]))
    render(<AttachmentsPanel container={{ id: 5, customs_status: 'BRAK' } as Container} />)
    expect(await screen.findByText(/Brak połączenia/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /upload|Wgraj/i })).toBeNull()
  })
})
