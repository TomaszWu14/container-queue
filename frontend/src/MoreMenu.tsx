import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useDismiss } from './ColumnFilter'

// Menu „Więcej” dla akcji drugorzędnych (audyt UI A27): przycisk + lista pozycji (role="menuitem").
// Zamyka się po wyborze pozycji, Escape, kliknięciu poza i przewinięciu (useDismiss).
export function MoreMenu({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  useDismiss(open, () => setOpen(false))
  return (
    <span className="more-menu" onClick={e => e.stopPropagation()}>
      <button type="button" className="btn secondary" aria-haspopup="menu" aria-expanded={open}
              onClick={() => setOpen(o => !o)}>
        {label} <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && <div className="more-menu-pop" role="menu" onClick={() => setOpen(false)}>{children}</div>}
    </span>
  )
}
