import { XIcon } from 'lucide-react'
// Kolejka Enterprise (plaster 5): zapisane widoki jako dodatkowe zakładki za wbudowanymi
// + „+ Zapisz widok". Mechanizm z dawnego menu „Widok" (queueViews, localStorage + prefs):
// URL (zakładka, zakres, filtry) + układ (grupowanie, kolumny, gęstość).
import { useLocation, useNavigate } from 'react-router-dom'
import { useT } from '../../i18n'
import type { ViewPrefs } from './useViewPrefs'
import { useConfirm } from '../../ConfirmDialog'

/** Czy bieżący URL to dokładnie zapisany widok (kolejność parametrów bez znaczenia). */
export function sameSearch(a: string, b: string): boolean {
  const norm = (s: string) => [...new URLSearchParams(s).entries()].map(([k, v]) => `${k}=${v}`).sort().join('&')
  return norm(a) === norm(b)
}

export default function SavedViewTabs({ p }: { p: ViewPrefs }) {
  const t = useT()
  const { prompt } = useConfirm()
  const location = useLocation()
  const navigate = useNavigate()
  return (
    <>
      {p.savedViews.map(v => {
        const active = sameSearch(location.search, v.search)
        return (
          <span key={v.name} className={`kq-saved${active ? ' active' : ''}`}>
            <button type="button" aria-pressed={active}
                    onClick={() => { p.applyViewLayout(v); navigate({ search: v.search }) }}>
              {v.name}
            </button>
            <button type="button" className="kq-saved-x" aria-label={`${t('deleteView')}: ${v.name}`}
                    title={t('deleteView')} onClick={() => p.deleteView(v.name)}><XIcon size={14} /></button>
          </span>
        )
      })}
      <button type="button" className="kq-save-view"
              onClick={async () => {
                const name = (await prompt(t('saveViewPrompt')))?.trim()
                if (name) p.saveView(name, location.search)
              }}>
        + {t('saveView')}
      </button>
    </>
  )
}
