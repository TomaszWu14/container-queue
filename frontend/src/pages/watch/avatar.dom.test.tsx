// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import UserAvatar, { avatarColor, initials } from './UserAvatar'

afterEach(cleanup)

describe('UserAvatar', () => {
  it('bez zdjęcia pokazuje inicjały na stałym kolorze', () => {
    render(<UserAvatar userId={5} name="Jan Kowalski" hasAvatar={false} />)
    const el = screen.getByText('JK')
    expect(el.getAttribute('style')).toContain(avatarColor(5))
    expect(initials('ala')).toBe('A')
  })

  it('ze zdjęciem ładuje /api/users/{id}/avatar, a błąd obrazka wraca do inicjałów', () => {
    render(<UserAvatar userId={7} name="Ala Nowak" hasAvatar />)
    const img = screen.getByRole('img', { name: 'Ala Nowak' })
    expect(img.getAttribute('src')).toContain('/api/users/7/avatar')
    fireEvent.error(img)
    expect(screen.getByText('AN')).toBeTruthy()
  })
})
