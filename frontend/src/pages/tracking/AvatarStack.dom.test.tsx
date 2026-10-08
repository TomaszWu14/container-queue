// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import AvatarStack, { uniqueWatchers } from './AvatarStack'

afterEach(cleanup)

const w = (id: number, has = false) => ({ user_id: id, name: `User ${id}`, has_avatar: has })

it('max 3 miniatury + licznik reszty; zdjęcie przez <image>, inaczej inicjały', () => {
  const { container } = render(<svg><AvatarStack watchers={[w(1, true), w(2), w(3), w(4), w(5)]} /></svg>)
  expect(container.querySelectorAll('.map-avatar')).toHaveLength(3)
  expect(container.querySelector('image')!.getAttribute('href')).toBe('/api/users/1/avatar')
  expect(container.textContent).toContain('+2')
})

it('pusty stos nic nie rysuje', () => {
  const { container } = render(<svg><AvatarStack watchers={[]} /></svg>)
  expect(container.querySelector('.map-avatar')).toBeNull()
})

it('uniqueWatchers scala po user_id z zachowaniem kolejności, duplikat liczony raz', () => {
  const points = [
    { watchers: [w(1), w(2)] },
    { watchers: [w(2), w(3)] },
    {},
  ]
  const result = uniqueWatchers(points)
  expect(result.map(x => x.user_id)).toEqual([1, 2, 3])
})
