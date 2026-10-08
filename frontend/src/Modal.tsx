import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react'
import { X } from 'lucide-react'
import { useT } from './i18n'

// Esc = wyjście dla modali z własnym backdropem (konwencja suity). `enabled` pozwala
// wyłączyć zamykanie w trakcie zapisu (busy). Stos: Esc zamyka tylko okno na wierzchu
// (np. potwierdzenie nad formularzem), a nie wszystkie otwarte naraz.
const escStack: Array<{ current: () => void }> = []
const onEscKey = (e: KeyboardEvent) => { if (e.key === 'Escape') escStack[escStack.length - 1]?.current() }

export function useEscClose(onClose: () => void, enabled = true) {
  const handler = useRef(onClose)
  useEffect(() => { handler.current = enabled ? onClose : () => {} })
  useEffect(() => {
    escStack.push(handler)
    if (escStack.length === 1) document.addEventListener('keydown', onEscKey)
    return () => {
      escStack.splice(escStack.indexOf(handler), 1)
      if (escStack.length === 0) document.removeEventListener('keydown', onEscKey)
    }
  }, [])
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), '
  + 'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Jedyny modal suity: Esc/klik w tło/X zamykają, `busy` blokuje zamknięcie w trakcie
// zapisu, `width` = maxWidth okna, `className` = dodatkowe klasy obok .modal.
// Fokus: wchodzi do okna, Tab krąży w środku, po zamknięciu wraca na element otwierający.
// Świadomie div, nie <dialog>.showModal(): top layer przykryłby toasty z portalu na body.
export function Modal({ title, onClose, children, width, className, busy = false }: {
  title: string
  onClose: () => void
  children: ReactNode
  width?: number
  className?: string
  busy?: boolean
}) {
  const t = useT()
  const box = useRef<HTMLDivElement>(null)
  // element otwierający zapamiętany przy pierwszym renderze — zanim autoFocus dziecka go przejmie
  const [opener] = useState(() => document.activeElement as HTMLElement | null)
  useEscClose(onClose, !busy)
  useEffect(() => {
    // [data-autofocus] zamiast autoFocus: przeżywa podwójny montaż efektów (StrictMode)
    if (!box.current?.contains(document.activeElement))
      (box.current?.querySelector<HTMLElement>('[data-autofocus]') ?? box.current)?.focus()
    return () => { if (opener?.isConnected) opener.focus() }
  }, [opener])
  const trapTab = (e: ReactKeyboardEvent) => {
    if (e.key !== 'Tab' || !box.current) return
    const items = Array.from(box.current.querySelectorAll<HTMLElement>(FOCUSABLE))
    if (items.length === 0) { e.preventDefault(); return }
    const first = items[0], last = items[items.length - 1]
    const active = document.activeElement
    if (e.shiftKey && (active === first || active === box.current)) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus() }
  }
  return (
    <div className="modal-backdrop" onClick={() => { if (!busy) onClose() }}>
      <div ref={box} className={className ? `modal ${className}` : 'modal'} role="dialog" aria-modal="true"
           aria-label={title} tabIndex={-1} style={width ? { maxWidth: width } : undefined}
           onClick={e => e.stopPropagation()} onKeyDown={trapTab}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="modal-x" aria-label={t('close')} title={t('close')}
                  disabled={busy} onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
