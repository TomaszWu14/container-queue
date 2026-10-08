import type { ReactNode } from 'react'

// Wspólny nagłówek strony (audyt UI B14/B15 — UX-023, UX-024): tytuł h1 zawsze widoczny,
// opcjonalny podtytuł i akcje strony po prawej (na wąskim ekranie zawijają się pod tytuł).
export function PageHeader({ title, subtitle, actions }: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="page-head">
      <div className="page-head-txt">
        <h1>{title}</h1>
        {subtitle && <p className="page-head-sub">{subtitle}</p>}
      </div>
      {actions && <div className="page-head-actions">{actions}</div>}
    </div>
  )
}
