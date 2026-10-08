import { useState } from 'react'
import { useT } from './i18n'
import { applyTheme, getStoredTheme, type Theme } from './theme'
import { Moon, Sun } from 'lucide-react'

/** #62 — przełącza motyw jasny/ciemny, trwałe w localStorage. `labelled` (menu użytkownika, C25):
 *  ikona bieżącego motywu + podpis „Motyw: ciemny” zamiast samego księżyca. */
export default function ThemeToggle({ labelled = false }: { labelled?: boolean }) {
  const t = useT()
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme())

  const toggle = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    applyTheme(next)
    localStorage.setItem('theme', next)
  }

  if (labelled) {
    const Icon = theme === 'dark' ? Moon : Sun
    return (
      <button type="button" className="tn-drop-link tn-theme-toggle labelled" onClick={toggle}
              title={t('themeToggle')}>
        <Icon size={16} aria-hidden="true" />
        {t('umTheme').replace('{mode}', t(theme === 'dark' ? 'umThemeDark' : 'umThemeLight'))}
      </button>
    )
  }
  return (
    <button type="button" className="tn-theme-toggle" onClick={toggle} title={t('themeToggle')}
            aria-label={t('themeToggle')}>
      {theme === 'dark' ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
    </button>
  )
}
