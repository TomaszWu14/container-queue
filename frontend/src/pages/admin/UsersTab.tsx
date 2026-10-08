import { BanIcon, CircleCheckIcon, MailIcon, PencilIcon, Trash2Icon } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import { useUser } from '../../App'
import { formatDateTime } from '../../dates'
import type { Company, Role, User } from '../../types'
import {
  DictTable, RoleAssignmentFields, isOnline, isPartnerRole, openInviteMail, rolePayload,
  useCompanies, useCustomsAgencies, useForwarders, useWarehouses,
} from './shared'
import { useConfirm } from '../../ConfirmDialog'

// modal-lite: sesje wybranego użytkownika z możliwością wylogowania (admin)
function UserSessions({ user, onClose }: { user: User; onClose: () => void }) {
  const t = useT()
  const [sessions, setSessions] = useState<{ id: number; created_at: string;
    expires_at: string; current: boolean }[]>([])
  const [error, setError] = useState('')
  const load = () => api.get<typeof sessions>(`/api/users/${user.id}/sessions`)
    .then(setSessions).catch(err => setError(errorMessage(err)))
  useEffect(() => { load() }, [])  // eslint-disable-line react-hooks/exhaustive-deps
  const revoke = async (sid: number) => {
    try { await api.del(`/api/users/${user.id}/sessions/${sid}`); load() }
    catch (err) { setError(errorMessage(err)) }
  }
  return (
    <div className="panel" style={{ margin: '10px 0', border: '1px solid var(--accent, #e0603a)' }}>
      <h3>{t('sessionsTitle')}: {user.login}</h3>
      {error && <p className="error">{error}</p>}
      {sessions.length === 0 && <p className="muted">{t('sessionsNone')}</p>}
      <table className="grid">
        <tbody>
          {sessions.map(s => (
            <tr key={s.id}>
              <td>{formatDateTime(s.created_at)}</td>
              <td>{formatDateTime(s.expires_at)}</td>
              <td>
                <button className="btn small secondary" onClick={() => revoke(s.id)}>
                  {t('logout')}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button className="btn secondary" style={{ marginTop: 8 }} onClick={onClose}>{t('cancel')}</button>
    </div>
  )
}

// „Podgląd jako rola" — admin dostaje tymczasowy token tylko-do-odczytu innej roli
function ImpersonateForm({ companies }: { companies: Company[] }) {
  const t = useT()
  const [role, setRole] = useState<Role>('logistics')
  const [companyId, setCompanyId] = useState('')
  const [error, setError] = useState('')
  const start = async () => {
    setError('')
    try {
      await api.post('/api/admin/impersonate',
        { role, ...(companyId ? { company_id: Number(companyId) } : {}) })
      window.location.assign('/')
    } catch (err) { setError(errorMessage(err)) }
  }
  return (
    <div className="row" style={{ margin: '12px 0', alignItems: 'center' }}>
      <strong>{t('impersonateTitle')}:</strong>
      <select aria-label={t('impersonateTitle')} value={role} onChange={e => setRole(e.target.value as Role)}>
        {(['logistics', 'warehouse', 'forwarder', 'customs', 'purchasing', 'sales'] as const)
          .map(r => <option key={r} value={r}>{t('roleName_' + r)}</option>)}
      </select>
      <select aria-label={t('company')} value={companyId} onChange={e => setCompanyId(e.target.value)}>
        <option value="">— {t('company')} —</option>
        {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
      <button type="button" className="btn secondary" onClick={start}>{t('impersonateStart')}</button>
      {error && <p className="error">{error}</p>}
    </div>
  )
}

export default function UsersTab() {
  const t = useT()
  const { confirm } = useConfirm()
  const me = useUser()
  const companies = useCompanies()
  const forwarders = useForwarders()
  const agencies = useCustomsAgencies()
  const warehouses = useWarehouses()
  const [users, setUsers] = useState<User[]>([])
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    login: '', email: '', full_name: '', password: '', role: 'logistics' as Role,
    company_id: '' as string, forwarder_id: '' as string, warehouse_id: '' as string,
    customs_agency_id: '' as string, view_all_companies: false, send_invite: false,
  })
  const [editing, setEditing] = useState<User | null>(null)
  const [editForm, setEditForm] = useState({
    full_name: '', email: '', role: 'logistics' as Role,
    company_id: '' as string, forwarder_id: '' as string, warehouse_id: '' as string,
    customs_agency_id: '' as string, view_all_companies: false, is_active: true, password: '',
  })
  const [editError, setEditError] = useState('')
  const [busy, setBusy] = useState(false)
  // hasło tymczasowe pokazane raz (nie trafia do mailto:) — admin przekazuje je osobno
  const [tempPass, setTempPass] = useState<{ login: string; password: string } | null>(null)
  // W14: magazyny dozwolone dla roli logistics (puste = wszystkie) + sesje per użytkownik
  const [allowedWh, setAllowedWh] = useState<number[]>([])
  const [sessionsFor, setSessionsFor] = useState<User | null>(null)

  const load = () => api.get<User[]>('/api/users').then(setUsers).catch(err => setError(errorMessage(err)))
  useEffect(() => { load() }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const wasInvite = form.send_invite
      const created = await api.post<User>('/api/users', { ...form, ...rolePayload(form) })
      // zaproszenie: otwórz Outlooka z gotową wiadomością (bez serwerowego SMTP)
      if (wasInvite && created.email && created.temp_password) {
        setTempPass({ login: created.login, password: created.temp_password })
        openInviteMail(created)
      }
      setForm({ login: '', email: '', full_name: '', password: '', role: 'logistics',
                company_id: '', forwarder_id: '', warehouse_id: '',
                customs_agency_id: '', view_all_companies: false, send_invite: false })
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  // ponowne zaproszenie: backend losuje nowe hasło tymczasowe, my otwieramy Outlooka
  const resendInvite = async (u: User) => {
    // reset hasła to realny skutek uboczny — user traci dotychczasowe hasło
    if (!(await confirm(`${t('resendInviteConfirm')} „${u.login}"?`, { danger: true }))) return
    setError('')
    try {
      const fresh = await api.post<User>(`/api/users/${u.id}/reset-invite`, {})
      if (fresh.temp_password) {
        setTempPass({ login: fresh.login, password: fresh.temp_password })
        openInviteMail(fresh)
      }
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const toggleActive = async (user: User) => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api.patch(`/api/users/${user.id}`, { is_active: !user.is_active })
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const removeUser = async (u: User) => {
    if (busy) return
    if (!(await confirm(`${t('deleteUserConfirm')} „${u.login}"?`, { danger: true }))) return
    setBusy(true)
    setError('')
    try {
      await api.del(`/api/users/${u.id}`)
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const startEdit = (u: User) => {
    setEditError('')
    setEditing(u)
    setEditForm({
      full_name: u.full_name, email: u.email ?? '', role: u.role,
      company_id: u.company_id ? String(u.company_id) : '',
      forwarder_id: u.forwarder_id ? String(u.forwarder_id) : '',
      warehouse_id: u.warehouse_id ? String(u.warehouse_id) : '',
      customs_agency_id: u.customs_agency_id ? String(u.customs_agency_id) : '',
      view_all_companies: u.view_all_companies, is_active: u.is_active, password: '',
    })
    setAllowedWh(u.allowed_warehouse_ids ?? [])
  }

  const saveEdit = async (event: FormEvent) => {
    event.preventDefault()
    if (!editing || busy) return
    setBusy(true)
    setEditError('')
    try {
      const payload: Record<string, unknown> = {
        full_name: editForm.full_name,
        email: editForm.email.trim(),
        role: editForm.role,
        ...rolePayload(editForm),
        is_active: editForm.is_active,
      }
      if (editForm.role === 'logistics') payload.allowed_warehouse_ids = allowedWh
      if (editForm.password) payload.password = editForm.password  // puste = bez zmiany hasła
      await api.patch(`/api/users/${editing.id}`, payload)
      setEditing(null)
      load()
    } catch (err) {
      setEditError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const disable2fa = async (u: User) => {
    if (!(await confirm(`${t('disable2faConfirm')} „${u.login}"?`, { danger: true }))) return
    setError('')
    try { await api.post(`/api/users/${u.id}/2fa/disable`, {}); load() }
    catch (err) { setError(errorMessage(err)) }
  }

  const companyName = (id: number | null) => companies.find((c: Company) => c.id === id)?.name ?? ''

  return (
    <div className="panel">
      <h3>{t('users')}</h3>
      <form className="row" onSubmit={submit} style={{ marginBottom: 12 }}>
        <input aria-label={t('loginField')} placeholder={t('loginField')} value={form.login} required
               onChange={e => setForm(f => ({ ...f, login: e.target.value }))} />
        <input aria-label={t('fullName')} placeholder={t('fullName')} value={form.full_name}
               onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} />
        <input aria-label={t('email')} placeholder={t('email')} type="email" value={form.email} required={form.send_invite}
               onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
        {!form.send_invite && (
          <input aria-label={t('password')} placeholder={t('password')} type="password" value={form.password} required minLength={8}
                 onChange={e => setForm(f => ({ ...f, password: e.target.value }))} />
        )}
        <select aria-label={t('role')} value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value as Role }))}>
          {(['logistics', 'warehouse', 'forwarder', 'customs', 'purchasing', 'sales', 'admin'] as const)
            .map(r => <option key={r} value={r}>{t('roleName_' + r)}</option>)}
        </select>
        <RoleAssignmentFields form={form} patch={p => setForm(f => ({ ...f, ...p }))}
          companies={companies} forwarders={forwarders} agencies={agencies} warehouses={warehouses} />
        {!isPartnerRole(form.role) && (
          <label className="row" style={{ fontSize: 14 }}>
            <input type="checkbox" checked={form.view_all_companies}
                   onChange={e => setForm(f => ({ ...f, view_all_companies: e.target.checked }))} />
            {t('viewAll')}
          </label>
        )}
        <label className="row" style={{ fontSize: 14 }} title={t('sendInviteHint')}>
          <input type="checkbox" checked={form.send_invite}
                 onChange={e => setForm(f => ({ ...f, send_invite: e.target.checked }))} />
          {t('sendInvite')}
        </label>
        <button className="btn" disabled={busy}>{t('add')}</button>
      </form>
      {error && <p className="error">{error}</p>}
      {tempPass && (
        <p className="info" role="status">
          {t('invitePassNotice')} <b>{tempPass.login}</b>:{' '}
          <code className="mono">{tempPass.password}</code>{' '}
          <button type="button" className="btn small secondary"
                  onClick={() => setTempPass(null)}>{t('close')}</button>
        </p>
      )}
      {editing && (
        <form className="row" onSubmit={saveEdit}
              style={{ marginBottom: 12, padding: 10, borderRadius: 8,
                       border: '1px solid var(--accent, #e0603a)', background: 'rgba(224,96,58,0.06)' }}>
          <strong style={{ alignSelf: 'center' }}>{t('edit')}: {editing.login}</strong>
          <input aria-label={t('fullName')} placeholder={t('fullName')} value={editForm.full_name}
                 onChange={e => setEditForm(f => ({ ...f, full_name: e.target.value }))} />
          <input aria-label={t('email')} placeholder={t('email')} type="email" value={editForm.email}
                 onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))} />
          <select aria-label={t('role')} value={editForm.role} onChange={e => setEditForm(f => ({ ...f, role: e.target.value as Role }))}>
            {(['logistics', 'warehouse', 'forwarder', 'customs', 'purchasing', 'sales', 'admin'] as const)
              .map(r => <option key={r} value={r}>{t('roleName_' + r)}</option>)}
          </select>
          <RoleAssignmentFields form={editForm} patch={p => setEditForm(f => ({ ...f, ...p }))}
            companies={companies} forwarders={forwarders} agencies={agencies} warehouses={warehouses} />
          {!isPartnerRole(editForm.role) && (
            <label className="row" style={{ fontSize: 14 }}>
              <input type="checkbox" checked={editForm.view_all_companies}
                     onChange={e => setEditForm(f => ({ ...f, view_all_companies: e.target.checked }))} />
              {t('viewAll')}
            </label>
          )}
          <label className="row" style={{ fontSize: 14 }}>
            <input type="checkbox" checked={editForm.is_active}
                   onChange={e => setEditForm(f => ({ ...f, is_active: e.target.checked }))} />
            {t('active')}
          </label>
          {editForm.role === 'logistics' && (
            <fieldset style={{ flexBasis: '100%', border: '1px solid var(--border, #dde3ec)',
                               borderRadius: 8, padding: 8 }}>
              <legend style={{ fontSize: 13 }}>{t('allowedWarehouses')}</legend>
              {warehouses.map(w => (
                <label key={w.id} style={{ marginRight: 12, fontSize: 14 }}>
                  <input type="checkbox" checked={allowedWh.includes(w.id)}
                         onChange={e => setAllowedWh(ids => e.target.checked
                           ? [...ids, w.id] : ids.filter(i => i !== w.id))} />
                  {' '}{w.name}
                </label>
              ))}
            </fieldset>
          )}
          <input aria-label={`${t('newPassword')} — ${t('pwKeepBlank')}`} placeholder={`${t('newPassword')} — ${t('pwKeepBlank')}`} type="password"
                 value={editForm.password} minLength={8}
                 onChange={e => setEditForm(f => ({ ...f, password: e.target.value }))} />
          <button type="button" className="btn secondary" onClick={() => setEditing(null)}>{t('cancel')}</button>
          <button className="btn" disabled={busy}>{t('save')}</button>
          {editError && <p className="error" style={{ flexBasis: '100%' }}>{editError}</p>}
        </form>
      )}
      <DictTable className="grid-status"
                 cols={[t('loginField'), t('fullName'), { label: t('role'), width: '140px' },
                        t('company'), { label: t('viewAll'), width: '90px' },
                        { label: t('active'), width: '90px' }, { label: t('actions'), width: '250px' }]}>
            {users.map(user => (
              <tr key={user.id}>
                <td>
                  <span className={`online-dot${isOnline(user.last_seen) ? ' on' : ''}`}
                        title={isOnline(user.last_seen) ? t('online')
                          : (user.last_seen
                              ? `${t('lastSeen')}: ${formatDateTime(user.last_seen)}`
                              : t('neverSeen'))} />
                  {user.login}
                </td>
                <td>{user.full_name}</td>
                <td>{t('roleName_' + user.role)}</td>
                <td>{companyName(user.company_id)}</td>
                <td>{user.view_all_companies ? t('yes') : ''}</td>
                <td>{user.is_active ? t('yes') : t('no')}</td>
                <td>
                  {/* B28: te same sloty w każdym wierszu (brak e-maila = nieaktywna koperta, a nie
                      przesunięte przyciski), ikony z nazwą dla czytnika, jeden rząd bez zawijania */}
                  <div className="row-actions">
                    <button className="btn small secondary" disabled={!user.email}
                            onClick={() => resendInvite(user)} aria-label={t('sendInvite')}
                            title={user.email ? t('sendInvite') : t('userNoEmail')}><MailIcon size={14} /></button>
                    <button className="btn small secondary" onClick={() => startEdit(user)}
                            aria-label={t('edit')} title={t('edit')}><PencilIcon size={14} /></button>
                    <button className="btn small secondary" disabled={busy} onClick={() => toggleActive(user)}
                            aria-label={user.is_active ? t('deactivate') : t('activate')}
                            title={user.is_active ? t('deactivate') : t('activate')}>
                      {user.is_active ? <BanIcon size={14} /> : <CircleCheckIcon size={14} />}
                    </button>
                    <button className="btn small danger" disabled={busy} onClick={() => removeUser(user)}
                            aria-label={t('deleteUser')} title={t('deleteUser')}><Trash2Icon size={14} /></button>
                    <button className="btn small secondary" onClick={() => setSessionsFor(user)}>
                      {t('sessionsBtn')}
                    </button>
                    {user.totp_enabled && user.id !== me?.id && (
                      <button className="btn small secondary" onClick={() => disable2fa(user)}>
                        {t('disable2faBtn')}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
      </DictTable>
      {sessionsFor && <UserSessions user={sessionsFor} onClose={() => setSessionsFor(null)} />}
      <ImpersonateForm companies={companies} />
    </div>
  )
}
