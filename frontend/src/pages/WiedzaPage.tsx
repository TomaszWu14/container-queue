import { BookOpen, Megaphone, MegaphoneIcon } from 'lucide-react'
// Moduł Wiedza (W16): tematy do omówienia (ranking wg głosów, statusy) oraz
// noty eskalacyjne (tworzenie per rola + widok kto przeczytał dla edytorów).
import { EmptyState, useToast } from '../feedback'
import { useCallback, useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { writesKnowledge } from '../routing'
import { useBusy } from '../useBusy'
import { useUser } from '../App'
import { useT } from '../i18n'
import { formatDateTime } from '../dates'
import type { BulletinAck, KnowledgeBulletin, Role, TrainingTopic } from '../types'
import { PageHeader } from '../PageHeader'
import { useCompanies } from './admin/shared'

const TOPIC_STATUSES = ['otwarty', 'zaplanowany', 'omowiony'] as const
const ALL_ROLES: Role[] = ['admin', 'logistics', 'warehouse', 'forwarder',
                           'customs', 'purchasing', 'sales']

export function TopicsTab() {
  const t = useT()
  const user = useUser()
  const canEdit = user?.role === 'admin' || user?.role === 'logistics'
  const canVote = writesKnowledge(user?.role)   // sprzedaż czyta, nie głosuje (backend 403)
  const { showToast } = useToast()
  const { busy, run } = useBusy()
  const [topics, setTopics] = useState<TrainingTopic[]>([])

  const reload = useCallback(() => {
    api.get<TrainingTopic[]>('/api/knowledge/topics').then(setTopics).catch(() => {})
  }, [])
  useEffect(() => { reload() }, [reload])

  // dwuklik „+1” = jeden głos; błąd → toast zamiast cichego unhandled rejection
  const update = (req: () => Promise<TrainingTopic>, id: number) => run(() => req()
    .then(updated => setTopics(list => list.map(x => (x.id === id ? updated : x))))
    .catch(err => showToast(errorMessage(err), 'error')))
  const vote = (id: number) =>
    update(() => api.post<TrainingTopic>(`/api/knowledge/topics/${id}/vote`, {}), id)
  const setStatus = (id: number, s: string) =>
    update(() => api.patch<TrainingTopic>(`/api/knowledge/topics/${id}/status?new_status=${s}`, {}), id)

  return (
    <div>
      {topics.length === 0 && <EmptyState icon={BookOpen} title={t('kbNoTopics')} />}
      {topics.map(topic => (
        <div key={topic.id} data-testid="kb-topic" style={{
          border: '1px solid var(--border, #dde3ec)', borderRadius: 8,
          padding: '10px 12px', marginBottom: 8, display: 'flex', gap: 12,
          alignItems: 'flex-start',
        }}>
          <button className="btn small" disabled={topic.my_vote || !canVote || busy}
                  title={topic.my_vote ? t('kbVoted') : t('kbVote')}
                  onClick={() => vote(topic.id)}
                  style={{ minWidth: 56 }}>
            +1 · <b data-testid="kb-votes">{topic.votes}</b>
          </button>
          <div style={{ flex: 1 }}>
            <b>{topic.title}</b>
            {topic.body && <div style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>
              {topic.body}</div>}
            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
              {topic.scope_type && `${topic.scope_type}: ${topic.scope_key} · `}
              {topic.created_by_name} · {formatDateTime(topic.created_at)}
            </div>
          </div>
          {canEdit ? (
            <select aria-label={t('status')} value={topic.status} disabled={busy}
                    onChange={e => setStatus(topic.id, e.target.value)}>
              {TOPIC_STATUSES.map(s => <option key={s} value={s}>{t(`kbSt_${s}`)}</option>)}
            </select>
          ) : (
            <span className="badge">{t(`kbSt_${topic.status}`)}</span>
          )}
        </div>
      ))}
    </div>
  )
}

function AcksView({ bulletinId }: { bulletinId: number }) {
  const t = useT()
  const [acks, setAcks] = useState<BulletinAck[] | null>(null)
  useEffect(() => {
    api.get<BulletinAck[]>(`/api/knowledge/bulletins/${bulletinId}/acks`)
      .then(setAcks).catch(() => setAcks([]))
  }, [bulletinId])
  if (!acks) return null
  return (
    <table style={{ width: '100%', fontSize: 13, marginTop: 8 }}>
      <thead><tr>
        <th style={{ textAlign: 'left' }}>{t('kbWho')}</th>
        <th style={{ textAlign: 'left' }}>{t('kbRole')}</th>
        <th style={{ textAlign: 'left' }}>{t('kbReadAt')}</th>
      </tr></thead>
      <tbody>
        {acks.map(a => (
          <tr key={a.user_id}>
            <td>{a.full_name || a.login}</td>
            <td>{a.role}</td>
            <td>{a.read_at
              ? <span style={{ color: 'var(--ok, #067647)' }}>✓ {formatDateTime(a.read_at)}</span>
              : <span style={{ color: 'var(--danger, #d92d20)' }}>{t('kbNotRead')}</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function BulletinsTab() {
  const t = useT()
  const user = useUser()
  const canEdit = user?.role === 'admin' || user?.role === 'logistics'
  // konto grupowe (admin / view_all) wybiera spółkę noty; logistyk jednej spółki — zawsze swoją
  const pickCompany = canEdit && (user?.role === 'admin' || !!user?.view_all_companies)
  const companies = useCompanies(canEdit)
  const companyName = (id: number | null) =>
    id === null ? t('kbWholeGroup') : companies.find(c => c.id === id)?.name ?? ''
  const [bulletins, setBulletins] = useState<KnowledgeBulletin[]>([])
  const [showAcks, setShowAcks] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const emptyForm = { title: '', body: '', roles: [] as Role[], company_id: null as number | null }
  const [form, setForm] = useState(emptyForm)
  const [error, setError] = useState('')
  const { busy, run } = useBusy()   // dwuklik „Wyślij” = jedna nota

  const reload = useCallback(() => {
    api.get<KnowledgeBulletin[]>('/api/knowledge/bulletins')
      .then(setBulletins).catch(() => {})
  }, [])
  useEffect(() => { reload() }, [reload])

  const toggleRole = (role: Role) => setForm(f => ({
    ...f,
    roles: f.roles.includes(role) ? f.roles.filter(r => r !== role) : [...f.roles, role],
  }))

  const send = async () => {
    if (!form.title.trim() || form.roles.length === 0) {
      setError(t('kbBulletinFormError')); return
    }
    setError('')
    await run(() => api.post('/api/knowledge/bulletins', form)
      .then(() => { setForm(emptyForm); setCreating(false); reload() })
      .catch(err => setError(errorMessage(err))))
  }

  return (
    <div>
      {canEdit && !creating && (
        <button className="btn" onClick={() => setCreating(true)}
                style={{ marginBottom: 12 }}>{t('kbNewBulletin')}</button>
      )}
      {creating && (
        <div style={{ display: 'grid', gap: 6, marginBottom: 16, maxWidth: 560 }}>
          <input aria-label={t('kbNoteTitle')} placeholder={t('kbNoteTitle')} value={form.title}
                 onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
          <textarea aria-label={t('kbNoteBody')} placeholder={t('kbNoteBody')} rows={4} value={form.body}
                    onChange={e => setForm(f => ({ ...f, body: e.target.value }))} />
          {pickCompany && (
            <select aria-label={t('kbBulletinCompany')} value={form.company_id ?? ''}
                    onChange={e => setForm(f => ({
                      ...f, company_id: e.target.value ? Number(e.target.value) : null }))}>
              <option value="">{t('kbWholeGroup')}</option>
              {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          )}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {ALL_ROLES.map(role => (
              <label key={role} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                <input type="checkbox" checked={form.roles.includes(role)}
                       onChange={() => toggleRole(role)} />{role}
              </label>
            ))}
          </div>
          {error && <p className="error" style={{ margin: 0 }}>{error}</p>}
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn" disabled={busy} onClick={send}>{t('kbSend')}</button>
            <button className="btn secondary" onClick={() => setCreating(false)}>
              {t('cancel')}</button>
          </div>
        </div>
      )}

      {bulletins.length === 0 && <EmptyState icon={Megaphone} title={t('kbNoBulletins')} />}
      {bulletins.map(b => (
        <div key={b.id} style={{
          border: '1px solid var(--border, #dde3ec)', borderRadius: 8,
          padding: '10px 12px', marginBottom: 8,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <b><MegaphoneIcon size={14} /> {b.title}
              {b.company_id !== undefined && companyName(b.company_id) && (
                <span className="badge st-ZAPOWIEDZIANY" style={{ marginLeft: 6 }}>
                  {companyName(b.company_id)}</span>
              )}</b>
            {canEdit && (
              <button className="btn small secondary"
                      onClick={() => setShowAcks(a => (a === b.id ? null : b.id))}>
                {t('kbWhoRead')}
              </button>
            )}
          </div>
          {b.body && <div style={{ whiteSpace: 'pre-wrap', fontSize: 14,
                                   marginTop: 4 }}>{b.body}</div>}
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            {t('kbRoles')}: {b.roles.join(', ')} · {b.created_by_name}
            {' · '}{formatDateTime(b.created_at)}
          </div>
          {showAcks === b.id && <AcksView bulletinId={b.id} />}
        </div>
      ))}
    </div>
  )
}

export default function WiedzaPage() {
  const t = useT()
  const [tab, setTab] = useState<'topics' | 'bulletins'>(
    () => (new URLSearchParams(window.location.search).get('tab') === 'noty'
      ? 'bulletins' : 'topics'))
  return (
    <main className="page">
      <PageHeader title={t('kbModule')} />
      <div style={{ display: 'flex', gap: 8, margin: '12px 0' }}>
        <button className={`btn small${tab === 'topics' ? '' : ' secondary'}`}
                onClick={() => setTab('topics')}>{t('kbTopicsTab')}</button>
        <button className={`btn small${tab === 'bulletins' ? '' : ' secondary'}`}
                onClick={() => setTab('bulletins')}>{t('kbBulletinsTab')}</button>
      </div>
      {tab === 'topics' ? <TopicsTab /> : <BulletinsTab />}
    </main>
  )
}
