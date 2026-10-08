import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useT } from './i18n'

type ToastType = 'success' | 'error'
type ToastAction = { label: string; onClick: () => void }
type Toast = { id: number; type: ToastType; message: string; action?: ToastAction }

const ToastContext = createContext<{
  showToast: (message: string, type?: ToastType, action?: ToastAction) => void
  // LoadError „zajmuje” komunikat: ten sam błąd nie idzie już toastem (zwraca zwolnienie)
  claim: (message: string) => () => void
}>({
  showToast: () => {},
  claim: () => () => {},
})

export function useToast() {
  return useContext(ToastContext)
}

const TOAST_TTL = 4000

// Jeden system toastów dla całej appki: kolejka w kontekście + portal na body,
// żeby nie zależeć od pozycji rodzica (position: fixed).
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const seq = useRef(0)
  const banners = useRef(new Map<string, number>())

  const dismiss = useCallback((id: number) => {
    setToasts(list => list.filter(toast => toast.id !== id))
  }, [])

  const showToast = useCallback((message: string, type: ToastType = 'success', action?: ToastAction) => {
    if (type === 'error' && banners.current.has(message)) return  // już widać go w banerze
    const id = ++seq.current
    // ten sam komunikat już wisi (np. jeden 500 z kilku zapytań strony) — nie mnożymy toastów
    setToasts(list => list.some(x => x.type === type && x.message === message)
      ? list : [...list, { id, type, message, action }])
    setTimeout(() => dismiss(id), action ? 10000 : TOAST_TTL)
  }, [dismiss])

  const claim = useCallback((message: string) => {
    const b = banners.current
    b.set(message, (b.get(message) ?? 0) + 1)
    setToasts(list => list.filter(x => !(x.type === 'error' && x.message === message)))
    return () => {
      const n = (b.get(message) ?? 1) - 1
      if (n) b.set(message, n)
      else b.delete(message)
    }
  }, [])

  return (
    <ToastContext.Provider value={{ showToast, claim }}>
      {children}
      {createPortal(
        <div className="toast-stack" aria-live="polite">
          {toasts.map(toast => (
            <div key={toast.id} className={`toast toast-${toast.type}`} role="button" tabIndex={0}
                 onClick={() => dismiss(toast.id)}
                 onKeyDown={e => { if (e.key === 'Enter' || e.key === 'Escape') dismiss(toast.id) }}>
              {toast.message}
              {toast.action && (
                <button type="button" className="toast-action"
                        onClick={e => { e.stopPropagation(); toast.action?.onClick(); dismiss(toast.id) }}>
                  {toast.action.label}
                </button>
              )}
            </div>
          ))}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  )
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  const t = useT()
  return (
    <div className="skeleton" role="status" aria-label={t('loading')}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-row" />
      ))}
    </div>
  )
}

// Szkielet aplikacji na czas /api/auth/me — pasek nawigacji + skeleton treści
// od razu, zamiast pustego ekranu (rola nieznana, więc bez linków menu).
export function AppSkeleton() {
  return (
    <div className="app-shell">
      <header className="topnav" />
      <div className="app-main"><main className="page"><Skeleton rows={8} /></main></div>
    </div>
  )
}

// Błąd wczytania danych strony: jeden baner z „Spróbuj ponownie” (bez toastów obok).
export function LoadError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const t = useT()
  const { claim } = useContext(ToastContext)
  useEffect(() => claim(message), [claim, message])
  return (
    <div className="load-error" role="alert">
      <AlertTriangle className="load-error-icon" size={18} aria-hidden="true" />
      <span>{message}</span>
      {onRetry && <button className="btn small secondary" onClick={onRetry}>{t('retry')}</button>}
    </div>
  )
}

// Pusty stan: ikona + tytuł + podpowiedź + opcjonalne akcje (dzieci — CTA zależne od roli).
// bare = bez własnej karty, gdy stan siedzi już w .panel (np. sekcje koszyka).
export function EmptyState({ icon: Icon, title, hint, bare, children }: {
  icon: LucideIcon; title: string; hint?: string; bare?: boolean; children?: ReactNode
}) {
  return (
    <div className={bare ? 'empty-state' : 'panel empty-state'}>
      <Icon className="empty-state-icon" size={28} strokeWidth={1.6} aria-hidden="true" />
      <p className="empty-state-title">{title}</p>
      {hint && <p className="empty-state-hint">{hint}</p>}
      {children && <div className="empty-state-actions">{children}</div>}
    </div>
  )
}
