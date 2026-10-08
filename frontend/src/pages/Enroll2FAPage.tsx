import { useT } from '../i18n'
import { TwoFactorSection } from './ProfilePage'

/*
 * SEC-006: konto administratora bez 2FA — po zalogowaniu zamiast panelu ekran włączania 2FA.
 * Backend do tego czasu odrzuca zapisy (403, backend/app/twofa_policy.py).
 */
export default function Enroll2FAPage({ onDone, onLogout }: { onDone: () => void; onLogout: () => void }) {
  const t = useT()
  return (
    <main className="page" style={{ maxWidth: 640, margin: '0 auto' }}>
      <h1>{t('enroll2faTitle')}</h1>
      <p className="muted">{t('enroll2faInfo')}</p>
      <TwoFactorSection onDone={onDone} />
      <button className="btn secondary" onClick={onLogout}>{t('logout')}</button>
    </main>
  )
}
