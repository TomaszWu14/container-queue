// Wspólny układ Administracji i Master data: menu boczne z grupami (na wąskim ekranie
// rozwijana lista), sekcja z adresu /<obszar>/<slug>, strona startowa z kafelkami.
// Renderowana jest tylko aktywna sekcja — każda pobiera wyłącznie swoje dane.
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, Navigate, NavLink, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useUser } from '../App'
import { useT } from '../i18n'
import { Forbidden, NotFound } from '../routing'
import { AREA_BASE, Area, SECTIONS, Section, canSee, legacyTarget, pathOf } from './sections'
import './SectionShell.css'

// Rozwijany panel dodatkowy (np. pełny formularz z dawnej Administracji) — treść montuje
// się dopiero po rozwinięciu, więc nie pobiera danych, dopóki nikt go nie otworzy.
export function SectionMore({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <details className="sec-more" onToggle={e => setOpen(e.currentTarget.open)}>
      <summary>{label}</summary>
      {open && children}
    </details>
  )
}

export default function SectionShell({ area, title, render }: {
  area: Area
  title: string
  render: (slug: string) => ReactNode
}) {
  const t = useT()
  const role = useUser()?.role
  const navigate = useNavigate()
  const { section } = useParams()
  const { search, hash } = useLocation()

  if (!section) {
    const legacy = legacyTarget(search, hash)
    if (legacy) return <Navigate to={legacy} replace />
  }
  const current = section ? SECTIONS.find(s => s.slug === section) : undefined
  if (section && !current) return <NotFound />
  // sekcja przeniesiona między Administracją a Master data — stary adres dalej działa
  if (current && current.area !== area) return <Navigate to={pathOf(current)} replace />
  if (current && !canSee(role, current)) return <Forbidden />

  const visible = SECTIONS.filter(s => s.area === area && canSee(role, s))
  const groups = [...new Set(visible.map(s => s.group))]
    .map(g => [g, visible.filter(s => s.group === g)] as [string, Section[]])

  return (
    // B31: strona startowa = kafle, bez menu bocznego (to samo 2×, a na telefonie 2× tytuł)
    <main className={current ? 'page sec-layout' : 'page'}>
      {current && <nav className="sec-nav" aria-label={title}>
        <Link to={AREA_BASE[area]} className="sec-title">{title}</Link>
        <select className="sec-select" aria-label={t('secPick')} value={current?.slug ?? ''}
                onChange={e => navigate(e.target.value
                  ? `${AREA_BASE[area]}/${e.target.value}` : AREA_BASE[area])}>
          <option value="">{t('secStart')}</option>
          {groups.map(([g, items]) => (
            <optgroup key={g} label={t(g)}>
              {items.map(s => <option key={s.slug} value={s.slug}>{t(s.label)}</option>)}
            </optgroup>
          ))}
        </select>
        <div className="sec-groups">
          {groups.map(([g, items]) => (
            <div key={g} className="sec-group" role="group" aria-label={t(g)}>
              <div className="sec-group-h">{t(g)}</div>
              {items.map(s => (
                <NavLink key={s.slug} to={pathOf(s)} className="sec-link">{t(s.label)}</NavLink>
              ))}
            </div>
          ))}
        </div>
      </nav>}
      <section className="sec-body">
        {current ? (
          <>
            <h1 className="sec-h">{t(current.label)}</h1>
            {render(current.slug)}
          </>
        ) : (
          <>
            <h1 className="sec-h">{title}</h1>
            {groups.map(([g, items]) => (
              <section key={g} className="sec-tiles-group">
                <h2>{t(g)}</h2>
                <div className="sec-tiles">
                  {items.map(s => (
                    <Link key={s.slug} to={pathOf(s)} className="sec-tile">{t(s.label)}</Link>
                  ))}
                </div>
              </section>
            ))}
          </>
        )}
      </section>
    </main>
  )
}
