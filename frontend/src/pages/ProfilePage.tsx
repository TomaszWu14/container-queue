import { FormEvent, useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { useUser } from '../App'
import { formatDateTime } from '../dates'
import AvatarSection from './profile/AvatarSection'
import { PageHeader } from '../PageHeader'

/*
 * Profil → Bezpieczeństwo: 2FA (każda rola; dla admina obowiązkowe — SEC-006) + lista
 * aktywnych sesji z możliwością wylogowania pojedynczej sesji i wszystkich innych.
 */

interface Session {
  id: number
  created_at: string
  expires_at: string
  current: boolean
}

// onDone: ekran wymuszonego włączenia 2FA (Enroll2FAPage) — „Dalej” po zapisaniu kodów
export function TwoFactorSection({ onDone }: { onDone?: () => void }) {
  const t = useT()
  const user = useUser()
  const [setup, setSetup] = useState<{ secret: string; otpauth_url: string } | null>(null)
  const [qr, setQr] = useState('')
  const [code, setCode] = useState('')
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!setup) { setQr(''); return }
    QRCode.toDataURL(setup.otpauth_url, { width: 200 }).then(setQr).catch(() => setQr(''))
  }, [setup])

  const startSetup = async () => {
    setBusy(true); setError('')
    try {
      setSetup(await api.post<{ secret: string; otpauth_url: string }>('/api/auth/2fa/setup', {}))
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  const enable = async (event: FormEvent) => {
    event.preventDefault()
    if (!setup) return
    setBusy(true); setError('')
    try {
      const out = await api.post<{ backup_codes: string[] }>('/api/auth/2fa/enable',
        { secret: setup.secret, code: code.trim() })
      setBackupCodes(out.backup_codes)
      setSetup(null)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  return (
    <div className="panel">
      <h2 className="as-h3">{t('twoFactorTitle')}</h2>
      {backupCodes ? (
        <div>
          <p className="error" style={{ fontWeight: 700 }}>{t('backupCodesWarn')}</p>
          <pre style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 15,
                        background: 'var(--panel-2, #f8fafc)', padding: 12, borderRadius: 8 }}>
            {backupCodes.join('\n')}
          </pre>
          <p className="muted">{t('twoFactorEnabled')}</p>
          {onDone && <button className="btn" onClick={onDone}>{t('enroll2faContinue')}</button>}
        </div>
      ) : user?.totp_enabled ? (
        <p>{t('twoFactorActiveInfo')}</p>
      ) : setup ? (
        <form onSubmit={enable} style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 420 }}>
          <p className="muted">{t('twoFactorScanHint')}</p>
          {qr && <img src={qr} alt="QR" width={200} height={200} loading="lazy" style={{ alignSelf: 'flex-start' }} />}
          <div style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 14,
                        wordBreak: 'break-all' }}>
            <div><b>{t('twoFactorSecret')}:</b> {setup.secret}</div>
            <div>{setup.otpauth_url}</div>
          </div>
          <label>{t('totpCodeLabel')}
            <input value={code} inputMode="numeric" autoComplete="one-time-code"
                   onChange={e => setCode(e.target.value)} />
          </label>
          <div>
            <button className="btn" disabled={busy || !code.trim()}>{t('twoFactorEnableBtn')}</button>{' '}
            <button type="button" className="btn secondary" onClick={() => setSetup(null)}>{t('cancel')}</button>
          </div>
        </form>
      ) : (
        <button className="btn" disabled={busy} onClick={startSetup}>{t('twoFactorEnableBtn')}</button>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  )
}

function SessionsSection() {
  const t = useT()
  const [sessions, setSessions] = useState<Session[]>([])
  const [error, setError] = useState('')

  const load = () => api.get<Session[]>('/api/auth/sessions')
    .then(setSessions).catch(err => setError(errorMessage(err)))
  useEffect(() => { load() }, [])

  const revoke = async (id: number) => {
    setError('')
    try { await api.del(`/api/auth/sessions/${id}`); load() }
    catch (err) { setError(errorMessage(err)) }
  }
  const revokeOthers = async () => {
    setError('')
    try { await api.post('/api/auth/sessions/revoke-others', {}); load() }
    catch (err) { setError(errorMessage(err)) }
  }

  // B32/C27: bieżąca sesja pierwsza, jej znacznik w kolumnie akcji (sama siebie nie wyloguje);
  // „Wyloguj wszystkie inne” nad listą i tylko gdy są inne sesje
  const sorted = [...sessions].sort((a, b) => Number(b.current) - Number(a.current))
  const others = sessions.some(s => !s.current)
  return (
    <div className="panel">
      <div className="row row-between sessions-head">
        <h2 className="as-h3">{t('sessionsTitle')}</h2>
        {others && <button className="btn small secondary" onClick={revokeOthers}>{t('sessionsRevokeOthers')}</button>}
      </div>
      {error && <p className="error">{error}</p>}
      <div className="table-scroll">
        <table className="grid sessions-table">
          <thead><tr><th>{t('sessionCreated')}</th><th>{t('sessionExpires')}</th><th>{t('actions')}</th></tr></thead>
          <tbody>
            {sorted.map(s => (
              <tr key={s.id}>
                <td>{formatDateTime(s.created_at)}</td>
                <td>{formatDateTime(s.expires_at)}</td>
                <td>
                  {s.current
                    ? <span className="badge sess-current">{t('sessionCurrent')}</span>
                    : <button className="btn small secondary" onClick={() => revoke(s.id)}>{t('logout')}</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function ProfilePage() {
  const t = useT()
  return (
    <main className="page">
      <PageHeader title={t('profileSecurity')} />
      <AvatarSection />
      <TwoFactorSection />
      <SessionsSection />
    </main>
  )
}
