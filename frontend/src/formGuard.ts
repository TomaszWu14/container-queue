// Anuluj / Esc / klik w tło przy niezapisanych zmianach pytają o porzucenie — wszystkie
// trzy drogi wyjścia z formularza idą przez tę samą funkcję (spójnie w całej aplikacji).
// Zamknięcie/odświeżenie karty z brudnym formularzem — natywne pytanie przeglądarki
// (beforeunload; własnego tekstu przeglądarki i tak nie pokazują).
import { useEffect } from 'react'
import { useT } from './i18n'
import { useConfirm } from './ConfirmDialog'

export function useDiscardGuard(dirty: boolean, onClose: () => void) {
  const t = useT()
  const { confirm } = useConfirm()
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])
  return async () => {
    if (dirty && !(await confirm(t('discardChanges'), { danger: true }))) return
    onClose()
  }
}
