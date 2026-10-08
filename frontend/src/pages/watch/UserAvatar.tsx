import { useState } from 'react'
import type { CSSProperties } from 'react'

const PALETTE = ['#2f6fb2', '#0e8a6a', '#8a5c00', '#7a4fb5', '#b2472f', '#2f8a9e', '#5c6b2f', '#a13d73']
export const avatarColor = (id: number) => PALETTE[Math.abs(id) % PALETTE.length]

export const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]!.toUpperCase()).join('') || '?'

/** Miniatura użytkownika: zdjęcie (GET /api/users/{id}/avatar, cookies) albo inicjały. */
export default function UserAvatar({ userId, name, hasAvatar, size = 24, rev }: {
  userId: number; name: string; hasAvatar: boolean; size?: number; rev?: number
}) {
  const [broken, setBroken] = useState(false)
  const box = { width: size, height: size, fontSize: Math.round(size * 0.42) }
  if (hasAvatar && !broken) {
    return <img className="user-avatar" alt={name} style={box} width={size} height={size} loading="lazy"
                src={`/api/users/${userId}/avatar${rev ? `?r=${rev}` : ''}`}
                onError={() => setBroken(true)} />
  }
  // ponytail: kolor przez custom property, nie `background` — jsdom normalizuje hex w
  // zwykłych właściwościach CSS do rgb(), co psuje asercję `toContain(avatarColor(id))` w testach
  return <span className="user-avatar initials" aria-hidden
               style={{ ...box, '--avatar-bg': avatarColor(userId) } as CSSProperties}>
    {initials(name)}
  </span>
}
