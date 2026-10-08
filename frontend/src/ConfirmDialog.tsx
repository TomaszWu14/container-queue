import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Modal } from './Modal'
import { useT } from './i18n'

// Potwierdzenia i krótkie pytania w oknie aplikacji zamiast window.confirm/prompt (audyt UI S3):
// spójny wygląd, polskie przyciski, ciemny motyw, fokus wraca na przycisk wywołujący.
type Ask = { message: string; danger?: boolean; confirmLabel?: string; input?: boolean }
type Pending = Ask & { resolve: (answer: string | null) => void }

// poza providerem (testy komponentów, strony bez App) — natywny fallback, ta sama semantyka
const ConfirmContext = createContext<(ask: Ask) => Promise<string | null>>(async ask =>
  ask.input ? window.prompt(ask.message) : window.confirm(ask.message) ? '' : null)

export function useConfirm() {
  const ask = useContext(ConfirmContext)
  return useMemo(() => ({
    // danger = akcja nieodwracalna: czerwony przycisk, fokus startowy na „Anuluj”
    confirm: (message: string, opts?: { danger?: boolean; confirmLabel?: string }) =>
      ask({ message, ...opts }).then(answer => answer !== null),
    prompt: (message: string) => ask({ message, input: true }),
  }), [ask])
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const t = useT()
  const [pending, setPending] = useState<Pending | null>(null)
  const [text, setText] = useState('')
  const ask = useCallback((a: Ask) => new Promise<string | null>(resolve => {
    setText('')
    setPending({ ...a, resolve })
  }), [])
  const done = (answer: string | null) => {
    pending?.resolve(answer)
    setPending(null)
  }
  return (
    <ConfirmContext.Provider value={ask}>
      {children}
      {pending && (
        <Modal title={t('confirm')} onClose={() => done(null)} width={460} className="confirm-dialog">
          <form onSubmit={e => { e.preventDefault(); done(pending.input ? text : '') }}>
            {pending.input
              ? <label className="confirm-field">{pending.message}
                  <input data-autofocus value={text} onChange={e => setText(e.target.value)} />
                </label>
              : <p className="confirm-message">{pending.message}</p>}
            <div className="actions">
              <button type="button" className="btn secondary" data-autofocus={pending.danger || undefined}
                      onClick={() => done(null)}>{t('cancel')}</button>
              <button type="submit" className={pending.danger ? 'btn danger-solid' : 'btn'}
                      data-autofocus={(!pending.danger && !pending.input) || undefined}>
                {pending.confirmLabel ?? t('confirm')}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </ConfirmContext.Provider>
  )
}
