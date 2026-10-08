// Menu „Widok": gęstość (Kompaktowy 28px / Komfortowy 38px) + wybór i kolejność kolumn. Stan w
// useViewPrefs (wybór/gęstość: localStorage per przeglądarka; kolejność: profil konta). Treść menu (ViewOptions) reużywa też menu „⋯" na wąskim ekranie.
import { useState } from 'react'
import { useDismiss } from '../../ColumnFilter'
import { useT } from '../../i18n'
import { BASE_COLUMNS, COLUMN_LABEL, EXTRA_COLUMNS, LOCKED_COLUMN } from './columns'
import type { ViewPrefs } from './useViewPrefs'
import { ChevronDown, ChevronUp, SlidersHorizontal } from 'lucide-react'

export function ViewOptions({ p }: { p: ViewPrefs }) {
  const t = useT()
  // sekcja w bieżącej kolejności; ↑/↓ zamienia z sąsiadem z tej samej sekcji (Nr nieruchomy)
  const section = (keys: readonly string[]) => {
    const list = p.colOrder.filter(k => keys.includes(k) && !p.roleHidden.has(k))
    const movable = list.filter(k => k !== LOCKED_COLUMN)
    return list.map(key => {
      const label = t(COLUMN_LABEL[key])
      const i = movable.indexOf(key)
      const step = (dir: -1 | 1, Icon: typeof ChevronUp, hint: string, off: boolean) => (
        <button type="button" className="kq-col-step" aria-label={`${t(hint)}: ${label}`} title={t(hint)}
                disabled={off} onClick={() => p.stepCol(key, dir, keys)}>
          <Icon size={14} aria-hidden="true" />
        </button>
      )
      return (
        <div key={key} className="kq-col-row">
          <label className={key === LOCKED_COLUMN ? 'locked' : undefined}>
            <input type="checkbox" checked={p.columns.has(key)} disabled={key === LOCKED_COLUMN}
                   onChange={() => p.toggleCol(key)} />
            {label}
          </label>
          {i >= 0 && <>
            {step(-1, ChevronUp, 'kqColMoveUp', i === 0)}
            {step(1, ChevronDown, 'kqColMoveDown', i === movable.length - 1)}
          </>}
        </div>
      )
    })
  }
  return (
    <>
      <div className="kq-ct">{t('kqDensity')}</div>
      {([[true, 'kqDensityCompact'], [false, 'kqDensityComfort']] as const).map(([d, key]) => (
        <label key={key}>
          <input type="radio" name="kq-density" checked={p.dense === d} onChange={() => p.setDense(d)} />
          {t(key)}
        </label>
      ))}
      <div className="kq-ct">{t('kqColumns')}</div>
      <p className="kq-col-hint">{t('kqColDragHint')}</p>
      {section(BASE_COLUMNS)}
      <div className="kq-ct">{t('kqColumnsMore')}</div>
      {section(EXTRA_COLUMNS)}
      <button type="button" className="btn small secondary" onClick={p.resetCols}>
        {t('kqColumnsReset')}
      </button>
      <button type="button" className="btn small secondary" onClick={p.resetOrder}>
        {t('kqColOrderReset')}
      </button>
    </>
  )
}

export default function ViewMenu({ p }: { p: ViewPrefs }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  useDismiss(open, () => setOpen(false))
  return (
    <span className="kq-cols" onClick={e => e.stopPropagation()}>
      <button type="button" className={`kq-ico${open ? ' on' : ''}`} aria-expanded={open}
              aria-label={t('kqView')} title={t('kqViewHint')} onClick={() => setOpen(o => !o)}>
        <SlidersHorizontal size={16} aria-hidden="true" />
      </button>
      {open && (
        <div className="kq-cols-pop" role="dialog" aria-label={t('kqView')}>
          <ViewOptions p={p} />
        </div>
      )}
    </span>
  )
}
