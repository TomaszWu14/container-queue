import { useContext, useState } from 'react'
import { api, errorMessage } from '../../api'
import { UserContext } from '../../App'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import UserAvatar from '../watch/UserAvatar'

/** Profil: zdjęcie użytkownika (upload / usuń) — miniatura w „Śledzone przez…" i na mapie.
 * I2: `has` idzie za kontekstem (reload po zapisie), nie za stanem z chwili montażu —
 * inaczej powrót na profil po wcześniejszej zmianie w innej karcie pokazuje starą wartość. */
export default function AvatarSection() {
  const t = useT()
  const { user, reload } = useContext(UserContext)
  const { showToast } = useToast()
  const [optimistic, setOptimistic] = useState<boolean | null>(null)
  const [rev, setRev] = useState(0)
  if (!user) return null
  const has = optimistic ?? Boolean(user.has_avatar)

  const upload = async (file: File | undefined) => {
    if (!file) return
    try {
      await api.upload('/api/me/avatar', file)
      setOptimistic(true); setRev(r => r + 1)
      reload()
    } catch (e) { showToast(errorMessage(e), 'error') }
  }
  const remove = async () => {
    try {
      await api.del('/api/me/avatar')
      setOptimistic(false)
      reload()
    } catch (e) { showToast(errorMessage(e), 'error') }
  }
  return (
    <div className="panel">
      <h2 className="as-h3">{t('avatarTitle')}</h2>
      <div className="row" style={{ alignItems: 'center', gap: 12 }}>
        <UserAvatar key={rev} userId={user.id} name={user.full_name || user.login}
                    hasAvatar={has} size={64} rev={rev} />
        <label className="btn secondary">
          {t('avatarChange')}
          <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden
                 onChange={e => { upload(e.target.files?.[0]); e.target.value = '' }} />
        </label>
        {has && <button className="btn secondary" onClick={remove}>{t('avatarRemove')}</button>}
      </div>
      <p className="muted">{t('avatarHint')}</p>
    </div>
  )
}
