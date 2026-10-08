import { useUser } from '../../App'
import type { EditValue } from './EditableTable'

// Wspólne drobiazgi zakładek Danych podstawowych (filtr aktywności, rola, parsowanie pól).

export type ActiveFilter = '' | 'active' | 'inactive'

export function useIsAdmin() {
  return useUser()?.role === 'admin'
}

export const str = (v: EditValue | undefined) => String(v ?? '').trim()
export const num = (v: EditValue | undefined) => {
  const s = str(v)
  return s === '' ? null : Number(s)
}
