// @vitest-environment jsdom
// I2: po uploadzie/usunięciu awatara profil musi odświeżyć kontekst użytkownika
// (reload), inaczej powrót na profil pokazuje starą wartość has_avatar.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
vi.mock('../../feedback', async orig => ({
  ...(await orig() as object), useToast: () => ({ showToast: vi.fn() }),
}))
const { apiUpload, apiDel } = vi.hoisted(() => ({
  apiUpload: vi.fn(() => Promise.resolve({ has_avatar: true })),
  apiDel: vi.fn(() => Promise.resolve({ has_avatar: false })),
}))
vi.mock('../../api', () => ({ api: { upload: apiUpload, del: apiDel }, errorMessage: String }))

import { UserContext } from '../../App'
import type { User } from '../../types/core'
import AvatarSection from './AvatarSection'

afterEach(() => { cleanup(); vi.clearAllMocks() })

const user = { id: 1, login: 'jan', full_name: 'Jan Kowalski', has_avatar: false } as User

describe('AvatarSection', () => {
  it('odświeża kontekst użytkownika po uploadzie', async () => {
    const reload = vi.fn()
    render(<UserContext.Provider value={{ user, reload }}><AvatarSection /></UserContext.Provider>)
    const file = new File(['x'], 'a.png', { type: 'image/png' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await act(async () => fireEvent.change(input, { target: { files: [file] } }))
    expect(apiUpload).toHaveBeenCalled()
    expect(reload).toHaveBeenCalled()
  })

  it('odświeża kontekst użytkownika po usunięciu', async () => {
    const reload = vi.fn()
    const withAvatar = { ...user, has_avatar: true }
    render(<UserContext.Provider value={{ user: withAvatar, reload }}><AvatarSection /></UserContext.Provider>)
    await act(async () => fireEvent.click(screen.getByText('avatarRemove')))
    expect(apiDel).toHaveBeenCalled()
    expect(reload).toHaveBeenCalled()
  })
})
