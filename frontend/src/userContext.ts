import { createContext, useContext } from 'react'
import type { User } from './types'

// Kontekst zalogowanego użytkownika — osobny moduł, by pasek nawigacji nie importował App
// (cykl). App re-eksportuje oba symbole: importy `from './App'` i mocki w testach bez zmian.
export const UserContext = createContext<{ user: User | null; reload: () => void }>({
  user: null,
  reload: () => {},
})

export function useUser() {
  return useContext(UserContext).user
}
