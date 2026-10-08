// @vitest-environment jsdom
// Pasek obecności: bez siebie, tylko online (z kropką), ekran w podpowiedzi bez czasu, nadmiar jako „+N”.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('./i18n', () => ({ useT: () => (key: string) => key }))
const post = vi.fn()
vi.mock('./api', () => ({ api: { post: (p: string, b: unknown) => post(p, b) } }))

import { PresenceBar } from './PresenceBar'

const here = (user_id: number, name: string, path = '/kolejka') =>
  ({ user_id, name, role: 'logistics', path, has_avatar: false })

afterEach(() => { cleanup(); post.mockReset() })

const mount = () => render(<MemoryRouter initialEntries={['/kalendarz']}><PresenceBar userId={1} /></MemoryRouter>)

describe('PresenceBar', () => {
  it('pokazuje innych online (bez siebie): kropka, imię · rola · ekran, bez czasu bezczynności', async () => {
    post.mockResolvedValue([here(1, 'Ja Sam'), here(2, 'Anna Nowak'), here(3, 'Jan Kowalski', '/kontenery/42')])
    mount()
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/presence', { path: '/kalendarz', active: true }))
    const items = await screen.findAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0].className).toContain('on')
    expect(items[0].title).toBe('Anna Nowak · roleName_logistics · queue')
    expect(items[1].className).toContain('on')
    expect(items[1].title).toBe('Jan Kowalski · roleName_logistics · pbContainer')
  })

  it('nikogo poza mną → brak paska; nadmiar ponad 5 jako „+N”', async () => {
    post.mockResolvedValueOnce([here(1, 'Ja Sam')])
    const { container, unmount } = mount()
    await waitFor(() => expect(post).toHaveBeenCalled())
    expect(container.querySelector('.pb-bar')).toBeNull()
    unmount()
    post.mockResolvedValue([2, 3, 4, 5, 6, 7, 8].map(i => here(i, `Osoba ${i}`)))
    mount()
    expect(await screen.findByText('+2')).toBeTruthy()
  })
})
