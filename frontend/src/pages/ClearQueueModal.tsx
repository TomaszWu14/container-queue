import { useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import { Modal } from '../components'
import { CONTAINER_STATUSES } from '../types'

export default function ClearQueueModal({ moduleCode, onDone, onClose }: {
  moduleCode: string
  onDone: (deleted: number) => void
  onClose: () => void
}) {
  const t = useT()
  const [before, setBefore] = useState('')
  const [keepStatuses, setKeepStatuses] = useState<Set<string>>(new Set())
  const [preview, setPreview] = useState<number | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const buildQuery = (dryRun: boolean) => {
    const params = new URLSearchParams({ company_code: moduleCode })
    if (dryRun) params.set('dry_run', 'true')
    else params.set('confirm', 'true')
    if (before) params.set('before', before)
    for (const s of keepStatuses) params.append('keep_statuses', s)
    return params.toString()
  }

  useEffect(() => {
    let cancelled = false
    setPreviewing(true)
    api.del<{ deleted: number }>(`/api/containers?${buildQuery(true)}`)
      .then(r => { if (!cancelled) setPreview(r.deleted) })
      .catch(err => { if (!cancelled) setError(errorMessage(err)) })
      .finally(() => { if (!cancelled) setPreviewing(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [before, [...keepStatuses].join(',')])

  const toggleStatus = (s: string) => {
    setKeepStatuses(prev => {
      const next = new Set(prev)
      if (next.has(s)) next.delete(s); else next.add(s)
      return next
    })
  }

  const doClear = async () => {
    setBusy(true)
    setError('')
    try {
      const r = await api.del<{ deleted: number }>(`/api/containers?${buildQuery(false)}`)
      onDone(r.deleted)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const n = preview ?? 0

  return (
    <Modal title={`${t('clearQueueModalTitle')} (${moduleCode})`} onClose={onClose} busy={busy}>
        <label style={{ display: 'block', fontSize: 14, color: 'var(--muted)', marginBottom: 10 }}>
          {t('clearQueueBeforeLabel')}
          <input type="date" value={before} onChange={e => setBefore(e.target.value)}
                 style={{ display: 'block', marginTop: 4 }} />
        </label>
        <div style={{ fontSize: 14, color: 'var(--muted)', marginBottom: 10 }}>
          {t('clearQueueKeepLabel')}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px', marginTop: 4 }}>
            {CONTAINER_STATUSES.map(s => (
              <label key={s} className="row" style={{ fontSize: 14 }}>
                <input type="checkbox" checked={keepStatuses.has(s)}
                       onChange={() => toggleStatus(s)} />
                {t(`st_${s}`)}
              </label>
            ))}
          </div>
        </div>
        <p>{t('clearQueuePreview').replace('{n}', previewing ? '…' : String(n))}</p>
        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button className="btn secondary" disabled={busy} onClick={onClose}>
            {t('cancel')}
          </button>
          <button className="btn danger" disabled={busy || previewing || n === 0} onClick={doClear}>
            {busy ? t('loading') : t('clearQueueConfirmBtn').replace('{n}', String(n))}
          </button>
        </div>
    </Modal>
  )
}
