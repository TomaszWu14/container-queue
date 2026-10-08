// Edytor kolorów motywu jasnego i ciemnego (tło, tekst, akcent, pasek górny, wiersze DLT / ACME /
// bez magazynu). Dwie warstwy, ten sam ekran:
//  - company (Administracja → Kolory): admin, dla wszystkich, zapis przez API,
//  - personal (menu → Moje kolory): każdy dla siebie, na wierzchu firmowych, profil konta (prefs.ts).
// Zapisujemy tylko różnice od punktu odniesienia (domyślne arkusze; dla osobistych: + firmowe).
import { useEffect, useMemo, useState } from 'react'
import { Check, TriangleAlert } from 'lucide-react'
import { api, errorMessage } from '../../../api'
import { useT } from '../../../i18n'
import { setPref } from '../../../prefs'
import {
  EMPTY, USER_KEY, applyThemeColors, companyColors, sanitize, setThemeColors, userColors,
  type Mode, type ThemeColors,
} from '../../../themeColors'
import { ColorPicker } from './ColorPicker'
import { ColorsPreview } from './ColorsPreview'
import { CHECKS, GROUPS, contrast, defaults } from './palette'

export type Scope = 'company' | 'personal'

export function ColorsEditor({ scope }: { scope: Scope }) {
  const t = useT()
  const [mode, setMode] = useState<Mode>('light')
  const [saved, setSaved] = useState<ThemeColors>(EMPTY)
  const [draft, setDraft] = useState<ThemeColors>(EMPTY)
  const [open, setOpen] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const [company, setCompany] = useState<ThemeColors>(() => companyColors())

  useEffect(() => {
    if (scope === 'personal') {
      const mine = userColors()
      setSaved(mine); setDraft(mine)
    }
    api.get<ThemeColors>('/api/theme-colors')
      .then(c => {
        const s = sanitize(c)
        setCompany(s)
        if (scope === 'company') { setSaved(s); setDraft(s) }
      })
      .catch(err => { if (scope === 'company') setError(errorMessage(err)) })
  }, [scope])

  // punkt odniesienia: domyślne arkusze, a dla kolorów osobistych — z nałożonymi firmowymi
  const base = useMemo(() => ({ ...defaults(mode), ...(scope === 'personal' ? company[mode] : {}) }),
                       [mode, scope, company])
  const effective = { ...base, ...draft[mode] }
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved)

  const pick = (token: string, hex: string | null) => {
    setNote('')
    setDraft(prev => {
      const next = { ...prev[mode] }
      if (hex === null || hex === base[token]) delete next[token]   // = domyślny, nie zapisujemy
      else next[token] = hex
      return { ...prev, [mode]: next }
    })
  }
  const save = async () => {
    setBusy(true); setError(''); setNote('')
    try {
      if (scope === 'company') {
        const out = sanitize(await api.put<ThemeColors>('/api/admin/theme-colors', draft))
        setSaved(out); setDraft(out); setThemeColors(out)
      } else {
        setPref(USER_KEY, JSON.stringify(draft))   // lokalnie od razu, do konta z debouncem
        setSaved(draft); applyThemeColors()
      }
      setNote(t('colSaved'))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel colors-admin">
      <h3>{t(scope === 'company' ? 'colTitle' : 'colMyTitle')}</h3>
      <p className="muted">{t(scope === 'company' ? 'colIntro' : 'colMyIntro')}</p>
      <div className="row" role="tablist" aria-label={t('colMode')} style={{ gap: 8 }}>
        {(['light', 'dark'] as const).map(m => (
          <button key={m} type="button" role="tab" aria-selected={mode === m}
                  className={`btn small ${mode === m ? '' : 'secondary'}`}
                  onClick={() => { setMode(m); setOpen(null) }}>
            {t(m === 'light' ? 'colModeLight' : 'colModeDark')}
            {Object.keys(draft[m]).length > 0 && <span className="badge">{Object.keys(draft[m]).length}</span>}
          </button>
        ))}
      </div>

      <div className="colors-layout">
        <div className="colors-groups">
          {GROUPS.map(g => (
            <section key={g.key} className="colors-group">
              <h4>{t(g.label)}</h4>
              {g.tokens.map(({ token, label }) => {
                const id = `${mode}${token}`
                const changed = token in draft[mode]
                return (
                  <div key={token} className="colors-token">
                    <button type="button" className="colors-swatch-btn" aria-expanded={open === id}
                            onClick={() => setOpen(open === id ? null : id)}>
                      <span className="colors-swatch" style={{ background: effective[token] }} />
                      <span>{t(label)}</span>
                      <code>{effective[token]}</code>
                      {changed && <span className="badge">{t('colChanged')}</span>}
                    </button>
                    {open === id && (
                      <ColorPicker value={effective[token]} fallback={base[token]}
                                   onPick={hex => pick(token, hex)} onReset={() => pick(token, null)} />
                    )}
                  </div>
                )
              })}
            </section>
          ))}
        </div>

        <aside className="colors-side">
          <h4>{t('colPreview')}</h4>
          <ColorsPreview colors={effective} />
          <h4>{t('colChecks')}</h4>
          <ul className="colors-checks">
            {CHECKS.map(c => {
              const r = contrast(effective[c.fg], effective[c.bg])
              const ok = r >= c.min
              return (
                <li key={c.label} className={ok ? 'ok' : 'warn'}>
                  {ok ? <Check size={14} aria-hidden="true" /> : <TriangleAlert size={14} aria-hidden="true" />}
                  {' '}{t(c.label)} <b>{r.toFixed(1).replace('.', ',')}</b>
                  {!ok && <span className="muted"> — {t('colChkLow').replace('{min}', String(c.min).replace('.', ','))}</span>}
                </li>
              )
            })}
          </ul>
        </aside>
      </div>

      {error && <p className="error">{error}</p>}
      {note && <p className="muted" role="status">{note}</p>}
      <div className="row" style={{ gap: 8 }}>
        <button type="button" className="btn" disabled={busy || !dirty} onClick={save}>{t('colSave')}</button>
        <button type="button" className="btn secondary" disabled={busy || !dirty}
                onClick={() => { setDraft(saved); setOpen(null) }}>{t('colDiscard')}</button>
        <button type="button" className="btn secondary" disabled={busy || !Object.keys(draft[mode]).length}
                onClick={() => setDraft(prev => ({ ...prev, [mode]: {} }))}>
          {t(mode === 'light' ? 'colResetLight' : 'colResetDark')}
        </button>
      </div>
    </div>
  )
}
