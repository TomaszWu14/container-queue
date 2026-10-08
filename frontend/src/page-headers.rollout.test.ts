// Strażnik skali tytułów stron (audyt UI S13/B16 — UX-008, UX-025): tytuł strony ma jeden rozmiar
// z tokena (--fs-xl) — bez stylu inline (19 px), klasy „as-h2” (24 px) i ikon/emoji w h1; strony
// z akcjami/podtytułem używają wspólnego PageHeader, a tytuły klasowe (pulpit, odprawa, kalendarz)
// biorą rozmiar z tokena zamiast 21 px.
import { describe, expect, it } from 'vitest'
import { readAppCss } from './appCss.testutil'

const pages = import.meta.glob(['./pages/*.tsx', '!./pages/*.test.tsx'],
  { query: '?raw', import: 'default', eager: true }) as Record<string, string>

describe('tytuły stron', () => {
  it('h1 bez stylu inline, bez „as-h2” i bez ikony w treści', () => {
    const bad = Object.entries(pages).flatMap(([path, src]) =>
      [...src.matchAll(/<h1\b[^>]*>(?:\s*<[A-Z]\w*Icon\b|[^<]*?\p{Extended_Pictographic})?/gu)]
        .filter(m => /style=\{|as-h2/.test(m[0]) || /<[A-Z]\w*Icon\b|\p{Extended_Pictographic}/u.test(m[0]))
        .map(m => `${path}: ${m[0].slice(0, 60)}`))
    expect(bad).toEqual([])
  })

  it('strony z akcjami/podtytułem na PageHeader', () => {
    for (const p of ['Complaints', 'Forwarding', 'SpecialCare', 'Tracking', 'Wiedza', 'Profile', 'Koszyk',
      'ChangesFeed', 'Gate']) {
      expect(pages[`./pages/${p}Page.tsx`], p).toMatch(/<PageHeader\b/)
    }
  })

  it('tytuły klasowe z tokena --fs-xl', () => {
    const css = readAppCss()
    for (const cls of ['dash-title', 'cs-title', 'cal-title']) {
      const rule = css.match(new RegExp(`\\.${cls} \\{([^}]*)\\}`))?.[1] ?? ''
      expect(rule, cls).toMatch(/font-size: var\(--fs-xl\)/)
    }
  })
})
