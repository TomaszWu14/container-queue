import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import type { DocSendTemplate } from '../../types'
import { useConfirm } from '../../ConfirmDialog'

/** W5 #36: szablony wysyłki dokumentów do agencji celnej.
 *  Placeholdery: {container_no}, {eta}, {lista_dokumentow}, {liczba}.
 *  Szablon bez agencji = domyślny; szablon agencji ma pierwszeństwo. */
export default function DocTemplatesTab() {
  const t = useT()
  const { confirm } = useConfirm()
  const [items, setItems] = useState<DocSendTemplate[]>([])
  const [agencies, setAgencies] = useState<{ id: number; name: string }[]>([])
  const [editing, setEditing] = useState<Partial<DocSendTemplate> | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api.get<DocSendTemplate[]>('/api/customs/doc-templates')
    .then(setItems).catch(err => setError(errorMessage(err)))
  useEffect(() => {
    load()
    api.get<typeof agencies>('/api/customs-agencies').then(setAgencies).catch(() => {})
  }, [])

  const save = async () => {
    if (!editing) return
    setBusy(true)
    setError('')
    const body = {
      customs_agency_id: editing.customs_agency_id ?? null,
      subject: editing.subject ?? '',
      body: editing.body ?? '',
    }
    try {
      if (editing.id) await api.patch(`/api/customs/doc-templates/${editing.id}`, body)
      else await api.post('/api/customs/doc-templates', body)
      setEditing(null)
      load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: number) => {
    if (!(await confirm(t('tplDeleteConfirm'), { danger: true }))) return
    try {
      await api.del(`/api/customs/doc-templates/${id}`)
      load()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>{t('docTemplates')}</h3>
        <button className="btn small" onClick={() => setEditing({})}>{t('add')}</button>
      </div>
      <p style={{ color: 'var(--muted)', fontSize: 14 }}>{t('docTemplatesInfo')}</p>
      {error && <p className="error">{error}</p>}
      {items.length === 0 && <p className="muted">{t('tplNone')}</p>}
      {items.length > 0 && (
        <table className="grid">
          <thead>
            <tr><th>{t('customsAgency')}</th><th>{t('tplSubject')}</th><th></th></tr>
          </thead>
          <tbody>
            {items.map(item => (
              <tr key={item.id}>
                <td>{item.customs_agency_name ?? t('tplDefault')}</td>
                <td>{item.subject || '—'}</td>
                <td>
                  <div className="row" style={{ gap: 6 }}>
                    <button className="btn small secondary"
                            onClick={() => setEditing(item)}>{t('edit')}</button>
                    <button className="btn small danger"
                            onClick={() => remove(item.id)}>{t('delete')}</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editing && (
        <div style={{ marginTop: 12, paddingTop: 8, borderTop: '1px solid var(--border)' }}>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <select aria-label={t('customsAgency')} value={editing.customs_agency_id ?? ''}
                    onChange={e => setEditing(ed => ({ ...ed,
                      customs_agency_id: e.target.value ? Number(e.target.value) : null }))}>
              <option value="">{t('tplDefault')}</option>
              {agencies.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <input style={{ flex: 1, minWidth: 260 }} aria-label={t('tplSubject')} placeholder={t('tplSubject')}
                   value={editing.subject ?? ''}
                   onChange={e => setEditing(ed => ({ ...ed, subject: e.target.value }))} />
          </div>
          <textarea rows={6} style={{ width: '100%', marginTop: 8 }}
                    aria-label={t('tplBody')} placeholder={t('tplBody')}
                    value={editing.body ?? ''}
                    onChange={e => setEditing(ed => ({ ...ed, body: e.target.value }))} />
          <p className="muted" style={{ fontSize: 13, margin: '4px 0' }}>
            {t('tplPlaceholders')}: {'{container_no} {eta} {lista_dokumentow} {liczba}'}
          </p>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn small secondary" disabled={busy}
                    onClick={() => setEditing(null)}>{t('cancel')}</button>
            <button className="btn small" disabled={busy} onClick={save}>{t('save')}</button>
          </div>
        </div>
      )}
    </div>
  )
}
