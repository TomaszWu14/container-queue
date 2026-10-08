import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'

// Matryca reguł powiadomień (tylko admin): typ zdarzenia × kanał × rola.
// Brak nadpisania = kanał włączony (zachowanie domyślne aplikacji).
type Rule = { kind: string; role: string; channel: string; enabled: boolean }
type RulesResponse = { kinds: string[]; channels: string[]; roles: string[]; rules: Rule[] }

const key = (kind: string, role: string, channel: string) => `${kind}|${role}|${channel}`

export default function NotificationRulesTab() {
  const t = useT()
  const { showToast } = useToast()
  const [data, setData] = useState<RulesResponse | null>(null)
  // tylko wyjątki (enabled=false); reszta = domyślnie włączone
  const [disabled, setDisabled] = useState<Set<string>>(new Set())
  const [role, setRole] = useState('logistics')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get<RulesResponse>('/api/notifications/rules').then(resp => {
      setData(resp)
      setDisabled(new Set(resp.rules.filter(r => !r.enabled)
        .map(r => key(r.kind, r.role, r.channel))))
    }).catch(err => showToast(errorMessage(err), 'error'))
  }, [showToast])

  if (!data) return <div className="panel"><p>{t('loading')}</p></div>

  const toggle = (kind: string, ruleRole: string, channel: string) => {
    const k = key(kind, ruleRole, channel)
    setDisabled(prev => {
      const next = new Set(prev)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      return next
    })
  }

  const save = async () => {
    setSaving(true)
    try {
      const body: Rule[] = [...disabled].map(k => {
        const [kind, ruleRole, channel] = k.split('|')
        return { kind, role: ruleRole, channel, enabled: false }
      })
      await api.put('/api/notifications/rules', body)
      showToast(t('saved'), 'success')
    } catch (err) {
      showToast(errorMessage(err), 'error')
    } finally {
      setSaving(false)
    }
  }

  const on = (kind: string, ruleRole: string, channel: string) =>
    !disabled.has(key(kind, ruleRole, channel))

  return (
    <div className="panel">
      <h3>{t('notifRulesTitle')}</h3>
      <p style={{ color: 'var(--muted)' }}>{t('notifRulesHint')}</p>
      <div className="row" style={{ marginBottom: 10 }}>
        <label>{t('notifRulesRole')}{' '}
          <select value={role} onChange={e => setRole(e.target.value)}>
            {data.roles.map(r => <option key={r} value={r}>{t('role_' + r)}</option>)}
          </select>
        </label>
        <button className="btn" onClick={save} disabled={saving}>{t('save')}</button>
      </div>
      <table className="grid dict-table rules-table">
        <thead>
          <tr>
            <th>{t('notifKind')}</th>
            <th>{t('notifChannelBell')}</th>
            <th>{t('notifChannelEmail')}</th>
            <th>{t('notifChannelTeams')}</th>
          </tr>
        </thead>
        <tbody>
          {data.kinds.map(kind => (
            <tr key={kind}>
              <td>{kind}</td>
              <td><input type="checkbox" aria-label={`${kind} bell`}
                         checked={on(kind, role, 'bell')}
                         onChange={() => toggle(kind, role, 'bell')} /></td>
              <td><input type="checkbox" aria-label={`${kind} email`}
                         checked={on(kind, role, 'email')}
                         onChange={() => toggle(kind, role, 'email')} /></td>
              {/* Teams jest globalny (webhook, nie per-user) — kolumna niezależna od roli */}
              <td><input type="checkbox" aria-label={`${kind} teams`}
                         checked={on(kind, '*', 'teams')}
                         onChange={() => toggle(kind, '*', 'teams')} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
