import { avatarColor, initials } from '../watch/UserAvatar'

export interface MapWatcher { user_id: number; name: string; has_avatar: boolean }

/** Scala watchers z kilku punktów mapy po user_id, zachowując kolejność pierwszego wystąpienia. */
export function uniqueWatchers(points: { watchers?: MapWatcher[] }[]): MapWatcher[] {
  const seen = new Map<number, MapWatcher>()
  for (const p of points) {
    for (const w of p.watchers ?? []) {
      if (!seen.has(w.user_id)) seen.set(w.user_id, w)
    }
  }
  return [...seen.values()]
}

/** Miniatury obserwujących przy markerze mapy (SVG, lokalny układ markera): max 3 + „+n". */
export default function AvatarStack({ watchers, r = 5, idPrefix = '' }: {
  watchers: MapWatcher[]; r?: number; idPrefix?: string
}) {
  if (watchers.length === 0) return null
  const shown = watchers.slice(0, 3)
  const rest = watchers.length - shown.length
  return (
    <g className="map-avatars" transform={`translate(${r * 1.6},${-r * 1.9})`} pointerEvents="none">
      {shown.map((w, i) => {
        const cx = i * r * 1.4
        const clip = `${idPrefix}-av-${w.user_id}`
        return (
          <g key={w.user_id} className="map-avatar">
            <title>{w.name}</title>
            <circle cx={cx} r={r} fill={avatarColor(w.user_id)} stroke="#fff" strokeWidth={r * 0.22} />
            {w.has_avatar ? (
              <>
                <clipPath id={clip}><circle cx={cx} r={r} /></clipPath>
                <image href={`/api/users/${w.user_id}/avatar`} x={cx - r} y={-r}
                       width={r * 2} height={r * 2} clipPath={`url(#${clip})`}
                       preserveAspectRatio="xMidYMid slice" />
              </>
            ) : (
              <text x={cx} y={r * 0.38} textAnchor="middle"
                    style={{ fontSize: r * 1.05, fontWeight: 700, fill: '#fff' }}>{initials(w.name)}</text>
            )}
          </g>
        )
      })}
      {rest > 0 && (
        <text x={shown.length * r * 1.4} y={r * 0.38}
              style={{ fontSize: r * 1.1, fontWeight: 700, fill: '#fff' }}>+{rest}</text>
      )}
    </g>
  )
}
