import { FormEvent, useContext, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api, login } from '../api'
import { LANGS, Lang, LangContext, useT } from '../i18n'

/*
 * Ekran wejścia — wariant „2b Panel logowania" z Claude Design (Landing.dc.html):
 * dzielona karta — granatowy panel z opisem systemu po lewej, formularz logowania
 * i wizytówka administratora po prawej. Strona jest jednocześnie stroną startową
 * (unauth "/" i "/login" renderują ten komponent). Realna logika logowania bez zmian
 * (login() → onLogin); loginField to login użytkownika, nie e-mail — konta zakłada
 * administrator. CSS zescopowany pod `.kl2` (globalne style aplikacji w styles.css).
 */

const STYLE = `
.kl2{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;
  background:#e8ecf2;font-family:'IBM Plex Sans','Segoe UI',system-ui,sans-serif;color:#1c2733}
.kl2 *{box-sizing:border-box}
.kl2-card{display:grid;grid-template-columns:minmax(0,1fr) 400px;width:100%;max-width:1180px;
  background:#fff;border:1px solid #dde3ec;border-radius:14px;overflow:hidden;
  box-shadow:0 10px 22px rgba(16,38,63,.08)}
.kl2-aside{display:flex;flex-direction:column;padding:38px 34px;color:#eaf2ff;
  background:linear-gradient(120deg,#0d1f36 0%,#14304f 55%,#1b3f68 100%)}
.kl2-brand{display:flex;align-items:center;gap:9px}
.kl2-mark{display:flex;align-items:center;justify-content:center;width:30px;height:30px;
  border-radius:8px;background:#1d3c5f}
.kl2-brand-name{font-size:14px;font-weight:800;letter-spacing:.06em;line-height:1.05}
.kl2-brand-sub{font-size:8px;font-weight:600;letter-spacing:.22em;color:#79aefc}
.kl2-aside h1{margin:0;max-width:520px;font-size:30px;line-height:1.25;font-weight:700;
  letter-spacing:-.01em;color:#eaf2ff}
.kl2-aside p{margin:14px 0 0;max-width:520px;font-size:15px;line-height:1.6;color:#c8d6e8}
.kl2-spacer{flex:1;min-height:26px}
.kl2-chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:22px}
.kl2-chips span{padding:4px 12px;border-radius:999px;background:rgba(255,255,255,.1);
  border:1px solid rgba(255,255,255,.2);font-size:12px;color:#eaf2ff}
.kl2-form{display:flex;flex-direction:column;gap:14px;padding:38px 30px}
.kl2-form h2{margin:0;font-size:17px;font-weight:700;color:#1c2733}
.kl2-form .kl2-note{margin-top:4px;font-size:13px;color:#536276}
.kl2-field label{display:block;margin-bottom:6px;font-size:12px;font-weight:600;color:#334155}
.kl2-field input{width:100%;padding:10px 12px;border:1px solid #dde3ec;border-radius:8px;
  background:#fff;color:#1c2733;font:inherit;font-size:15px;outline:none;
  transition:border-color .15s,box-shadow .15s}
.kl2-field input:focus{border-color:#0b5fff;box-shadow:0 0 0 3px rgba(11,95,255,.15)}
.kl2-row{display:flex;align-items:center;justify-content:space-between;gap:10px}
.kl2-forgot{background:none;border:none;padding:0;font:inherit;font-size:13px;color:#0b5fff;cursor:pointer}
.kl2-forgot:hover{text-decoration:underline}
.kl2-demo{margin:0;padding:8px 10px;border-radius:6px;font-size:13px;background:var(--info-bg);color:var(--text)}
.kl2-submit{width:100%;padding:11px 20px;border:1px solid transparent;border-radius:8px;
  background:#0b5fff;color:#fff;font:inherit;font-size:15px;font-weight:700;cursor:pointer;
  transition:background .15s,transform .08s}
.kl2-submit:hover:not(:disabled){background:#0a55e6}
.kl2-submit:active:not(:disabled){transform:translateY(1px)}
.kl2-submit:disabled{background:#e2e8f0;color:#536276;cursor:not-allowed}
.kl2-error{margin:0;color:#b42318;font-size:13px;font-weight:600}
.kl2-hr{height:1px;background:#eef2f7;margin:4px 0}
.kl2-fwd{font-size:13px;line-height:1.5;color:#536276}
.kl2-admin{padding:12px 14px;border:1px solid #dde3ec;border-radius:12px;background:#f8fafc}
.kl2-admin-label{font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#536276}
.kl2-admin-name{margin-top:6px;font-size:14px;font-weight:600;color:#1c2733}
.kl2-admin a{display:inline-block;margin-top:2px;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:13px;color:#0b5fff;text-decoration:none}
.kl2-admin a:hover{text-decoration:underline}
.kl2-admin-help{margin-top:6px;font-size:13px;line-height:1.45;color:#536276}
.kl2-foot{display:flex;align-items:center;gap:6px;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:12px;color:#536276}
.kl2-foot button{background:none;border:none;padding:0;font:inherit;color:#536276;cursor:pointer}
.kl2-foot button.active,.kl2-foot button:hover{color:#0b5fff}
@media(max-width:900px){.kl2-card{grid-template-columns:1fr}.kl2-aside{padding:28px 22px}
  .kl2-aside h1{font-size:22px}.kl2{padding:12px}}
@media(prefers-reduced-motion:reduce){.kl2 *{transition:none!important}}
`

const CHIPS = ['Awizacje', 'Limity magazynów', 'Odprawa celna', 'Zlecenia transportowe', 'Powiadomienia']

export default function LoginPage({ onLogin }: { onLogin: () => void }) {
  const t = useT()
  const navigate = useNavigate()
  const { lang, setLang } = useContext(LangContext)
  const [username, setUsername] = useState('')
  // instancja portfolio: dane konta demo z /api/public/branding (puste = zwykła instancja)
  const [demoHint, setDemoHint] = useState('')
  useEffect(() => {
    api.get<{ demo_hint?: string }>('/api/public/branding')
      .then(b => setDemoHint(typeof b?.demo_hint === 'string' ? b.demo_hint : '')).catch(() => {})
  }, [])
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  // 2FA: drugi krok logowania — backend zwrócił pending_token zamiast cookies
  const [pendingToken, setPendingToken] = useState('')
  const [totpCode, setTotpCode] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const result = await login(username, password)
      if (result.totp_required && result.pending_token) {
        setPendingToken(result.pending_token)
      } else {
        onLogin()
      }
    } catch (err) {
      // tylko 401 = złe dane; 5xx/sieć nie może udawać "błędny login lub hasło"
      setError(err instanceof ApiError && err.status === 401 ? t('loginError') : t('loginServerError'))
    } finally {
      setBusy(false)
    }
  }

  const submitTotp = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.post('/api/auth/2fa/verify', { pending_token: pendingToken, code: totpCode.trim() })
      onLogin()
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? t('totpBadCode') : t('loginServerError'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="kl2">
      <style>{STYLE}</style>
      <div className="kl2-card">
        <aside className="kl2-aside">
          <div className="kl2-brand">
            <span className="kl2-mark">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#eaf2ff"
                   strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="8" width="13" height="9" rx="1" /><path d="M15 11h4l3 3v3h-7z" />
                <circle cx="6" cy="19" r="1.6" /><circle cx="17" cy="19" r="1.6" />
              </svg>
            </span>
            <span>
              <div className="kl2-brand-name">KOLEJKA</div>
              <div className="kl2-brand-sub">CONTAINER FLOW</div>
            </span>
          </div>
          <div className="kl2-spacer" />
          <h1>{t('loginAsideTitle')}</h1>
          <p>{t('loginAsideBody')}</p>
          <div className="kl2-chips">
            {CHIPS.map(c => <span key={c}>{c}</span>)}
          </div>
        </aside>

        <main className="kl2-form">
          <div>
            <h2>{t('login')}</h2>
            <div className="kl2-note">{t('loginAccountsInfo')}</div>
          </div>
          {pendingToken ? (
            <form onSubmit={submitTotp} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div className="kl2-note">{t('totpStepInfo')}</div>
              <div className="kl2-field">
                <label htmlFor="kl2-totp">{t('totpCodeLabel')}</label>
                <input id="kl2-totp" type="text" inputMode="numeric" autoComplete="one-time-code"
                       autoFocus placeholder="123456" value={totpCode}
                       onChange={e => setTotpCode(e.target.value)} />
              </div>
              {error && <p className="kl2-error">{error}</p>}
              <button className="kl2-submit" type="submit" disabled={busy || !totpCode.trim()}>
                {t('totpVerify')}
              </button>
              <button type="button" className="kl2-forgot"
                      onClick={() => { setPendingToken(''); setTotpCode(''); setError('') }}>
                {t('backToLogin')}
              </button>
            </form>
          ) : (
          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {demoHint && <p className="kl2-demo" data-testid="demo-hint">{t('demoLoginHint')}: <b>{demoHint}</b></p>}
            <div className="kl2-field">
              <label htmlFor="kl2-login">{t('loginField')}</label>
              <input id="kl2-login" type="text" autoComplete="username" autoFocus
                     placeholder="np. m.kowalski" value={username}
                     onChange={e => setUsername(e.target.value)} />
            </div>
            <div className="kl2-field">
              <label htmlFor="kl2-pass">{t('password')}</label>
              <input id="kl2-pass" type="password" autoComplete="current-password"
                     placeholder="••••••••" value={password}
                     onChange={e => setPassword(e.target.value)} />
            </div>
            <div className="kl2-row">
              <span />
              <button type="button" className="kl2-forgot" onClick={() => navigate('/forgot-password')}>
                {t('forgotPassword')}
              </button>
            </div>
            {error && <p className="kl2-error">{error}</p>}
            <button className="kl2-submit" type="submit" disabled={busy || !username || !password}>
              {t('login')}
            </button>
          </form>
          )}
          <div className="kl2-hr" />
          <div className="kl2-fwd">{t('loginForwarderHint')}</div>
          <div style={{ flex: 1 }} />
          <div className="kl2-admin">
            <div className="kl2-admin-label">{t('loginAdminLabel')}</div>
            <div className="kl2-admin-name">Administrator systemu</div>
            <a href="mailto:admin@example.com">admin@example.com</a>
            <div className="kl2-admin-help">{t('loginAdminHelp')}</div>
          </div>
          <div className="kl2-foot">
            kolejka.example.com ·
            {LANGS.map(l => (
              <button key={l} type="button" className={lang === l ? 'active' : ''}
                      onClick={() => setLang(l as Lang)}>{l.toUpperCase()}</button>
            ))}
          </div>
        </main>
      </div>
    </div>
  )
}
