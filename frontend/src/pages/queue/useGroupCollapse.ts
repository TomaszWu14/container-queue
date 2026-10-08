// Zwijanie grup kolejki — dwa poziomy: grupa (dzień/etap/magazyn, strzałka) i sekcja planowania
// (Potwierdzone/Wysłane/Propozycje — przełącznik GLOBALNY dla wszystkich grup, pamiętany w prefs).
// Bug 2026-09-30: po zwinięciu „Propozycje" we wszystkich dniach strzałka dnia nie pokazywała
// wierszy (sekcja zostawała zwinięta globalnie). Teraz strzałka zwiniętego dnia go OTWIERA:
// dzień trafia do `opened` i pokazuje wszystkie swoje sekcje mimo globalnego zwinięcia.
// Ostatnia akcja wygrywa: globalny przełącznik sekcji czyści ręcznie otwarte dni.
import { useEffect, useState } from 'react'

export function useGroupCollapse(
  collapsedPlanning: string[], togglePlanGlobal: (status: string) => void, resetKey: string,
) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [opened, setOpened] = useState<Set<string>>(new Set())
  // nowa zakładka/zakres/grupowanie = wszystko rozwinięte, bez ręcznych wyjątków
  useEffect(() => { setCollapsed(new Set()); setOpened(new Set()) }, [resetKey])
  useEffect(() => { setOpened(new Set()) }, [collapsedPlanning])

  const edit = (set: typeof setCollapsed, key: string, on: boolean) => set(prev => {
    const next = new Set(prev)
    if (on) next.add(key); else next.delete(key)
    return next
  })
  // open = czy grupa pokazuje teraz jakiekolwiek wiersze (liczy EnterpriseGroup)
  const toggleGroup = (key: string, open: boolean) => {
    edit(setCollapsed, key, open)
    edit(setOpened, key, !open)
  }
  // sekcja w ręcznie otwartym dniu: klik oddaje dzień ustawieniu globalnemu (zwija ją z powrotem)
  const togglePlanSection = (status: string, groupKey?: string) => {
    if (groupKey !== undefined && opened.has(groupKey)) edit(setOpened, groupKey, false)
    else togglePlanGlobal(status)
  }
  return { collapsed, setCollapsed, opened, toggleGroup, togglePlanSection }
}
