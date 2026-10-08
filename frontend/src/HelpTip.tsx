// Ikona pomocy kontekstowej — mały „?" z popoverem, zamykany wzorcem useDismiss
// (Escape / klik poza / scroll), tak jak inne popovery w kolejce (ColumnFilter.tsx).
import { useState } from 'react'
import { useDismiss } from './ColumnFilter'

export function HelpTip({ text, label, icon = '?' }: { text: string; label: string; icon?: string }) {
  const [open, setOpen] = useState(false)
  useDismiss(open, () => setOpen(false))
  return (
    <span className="help-tip" onClick={e => e.stopPropagation()}>
      <button type="button" className="help-tip-btn" aria-label={label}
              onClick={() => setOpen(v => !v)}>{icon}</button>
      {open && <span className="help-pop" role="tooltip">{text}</span>}
    </span>
  )
}
