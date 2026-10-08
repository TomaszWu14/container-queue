// Sekcja „Profil dokumentów” na karcie dostawcy: status, pokrycie map CI/PL, słowa kluczowe,
// tolerancje, wynik ostatniego testu próbek; admin otwiera kreator (Skonfiguruj/Edytuj)
// i ustawia wymagane dokumenty (RequiredDocsEditor).
import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useUser } from '../../App'
import { useT } from '../../i18n'
import { mappedCount, type Profile } from './profileModel'
import ProfileWizard from './ProfileWizard'
import RequiredDocsEditor from './RequiredDocsEditor'
import './profile.css'

export const PROFILE_READERS = ['admin', 'logistics', 'purchasing']

export default function DocProfileCard({ supplierId, supplierName }: { supplierId: number; supplierName: string }) {
  const t = useT()
  const user = useUser()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)
  const [rev, setRev] = useState(0)          // zamknięcie kreatora = świeży odczyt (próbki, status)
  const canEdit = user?.role === 'admin'

  useEffect(() => {
    let live = true
    api.get<Profile>(`/api/suppliers/${supplierId}/doc-profile`)
      .then(p => { if (live) setProfile(p) })
      .catch(err => { if (live) setError(errorMessage(err)) })
    return () => { live = false }
  }, [supplierId, rev])

  if (error) return <section className="panel"><h3>{t('sdpTitle')}</h3><p className="error">{error}</p></section>
  if (!profile) return null
  const status = profile.id === null ? 'none' : profile.status
  const tested = profile.samples.filter(s => s.last_test && 'ok' in s.last_test)
  const okCount = tested.filter(s => s.last_test.ok).length

  return (
    <section className="panel sdp-card" aria-label={t('sdpTitle')}>
      <div className="sdp-card-head">
        <div>
          <h3>{t('sdpTitle')} <span className={`sdp-status ${status}`}>{t(`sdpStatus_${status}`)}</span></h3>
          <p className="muted txt-sm">{t('sdpHint')}</p>
        </div>
        {canEdit && (
          <button type="button" className="btn small" onClick={() => setOpen(true)}>
            {status === 'none' ? t('sdpConfigure') : t('sdpEdit')}
          </button>
        )}
      </div>
      {status !== 'none' && (
        <div className="sdp-card-grid">
          <div>
            <b>{profile.currency || '—'}</b> · {profile.doc_language || '—'}
            <div className="sdp-cov">
              {(['ci', 'pl'] as const).map(k => {
                const n = mappedCount(profile[k === 'ci' ? 'ci_map' : 'pl_map'])
                return (
                  <span key={k} className={n ? 'sdp-pill ok' : 'sdp-pill'}>
                    {t('sdpCoverage').replace('{kind}', k.toUpperCase()).replace('{n}', String(n))}
                  </span>
                )
              })}
            </div>
          </div>
          <div>
            <span className="muted txt-xs">{t('sdpKeywords')}</span>
            <div className="sdp-chips">
              {profile.keywords.length ? profile.keywords.map(k => <span key={k} className="chip">{k}</span>) : '—'}
            </div>
          </div>
          <div>
            <span className="muted txt-xs">{t('sdpTolerances')}</span>
            <div className="mono txt-sm">
              {t('sdpTolAmount')}: {profile.tol_amount_pct} · {t('sdpTolQty')}: {profile.tol_qty_pct}
            </div>
          </div>
          <div>
            <span className={tested.length && okCount === tested.length ? 'sdp-pill ok' : 'sdp-pill'}>
              {tested.length
                ? t('sdpSamplesOk').replace('{ok}', String(okCount)).replace('{n}', String(tested.length))
                : t('sdpNoSamples')}
            </span>
          </div>
        </div>
      )}
      <RequiredDocsEditor supplierId={supplierId} value={profile.required_docs} canEdit={canEdit}
                          onSaved={codes => setProfile({ ...profile, required_docs: codes })} />
      {open && (
        <ProfileWizard supplierId={supplierId} supplierName={supplierName} profile={profile}
                       onClose={() => { setOpen(false); setRev(r => r + 1) }} />
      )}
    </section>
  )
}
