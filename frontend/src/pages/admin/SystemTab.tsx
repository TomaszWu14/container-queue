import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import MonitorTabs from './logs/MonitorTabs'
import { formatDateTime } from '../../dates'

interface BackupVerify {
  status: string
  detail: string
  started_at: string | null
  dump?: string
  tables?: number
}

interface SystemInfo {
  version: string
  built_at: string
  uptime_s: number
  database: string
  run_background_jobs: boolean
  last_tracking_sync: string | null
  last_ais_seen: string | null
  last_po_import: string | null
  last_container_created: string | null
  client_errors_24h: number
  uploads_size_mb: number
  backup_verify: BackupVerify | null
}

interface Integration {
  key: string; label: string; status: 'on' | 'off'; detail: string; last_signal: string | null
}

const fmtUptime = (s: number) => {
  const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60)
  return d > 0 ? `${d}d ${h}h ${m}m` : `${h}h ${m}m`
}

export default function SystemTab() {
  const t = useT()
  const [info, setInfo] = useState<SystemInfo | null>(null)
  const [error, setError] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [verify, setVerify] = useState<BackupVerify | null>(null)
  const [integrations, setIntegrations] = useState<Integration[] | null>(null)

  useEffect(() => {
    api.get<SystemInfo>('/api/admin/system')
      .then(i => { setInfo(i); setVerify(i.backup_verify) })
      .catch(err => setError(errorMessage(err)))
    api.get<{ integrations: Integration[] }>('/api/admin/integrations')
      .then(r => setIntegrations(r.integrations)).catch(() => {})
  }, [])

  const runVerify = async () => {
    setVerifying(true); setError('')
    try {
      setVerify(await api.post<BackupVerify>('/api/admin/system/verify-backup', {}))
    } catch (err) { setError(errorMessage(err)) } finally { setVerifying(false) }
  }

  const dt = (iso: string | null) => (iso ? formatDateTime(iso) : '—')
  const row = (label: string, value: ReactNode) => (
    <><dt style={{ color: 'var(--muted)' }}>{label}</dt><dd style={{ margin: 0 }}>{value}</dd></>
  )

  return (
    <div className="panel">
      <h3>{t('sysTabTitle')}</h3>
      {error && <p className="error">{error}</p>}
      {info && (
        <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '4px 16px', margin: 0 }}>
          {row(t('sysVersion'), `${info.version} (${dt(info.built_at)})`)}
          {row(t('sysUptime'), fmtUptime(info.uptime_s))}
          {row(t('sysDatabase'), info.database)}
          {row(t('sysBgJobs'), info.run_background_jobs ? t('sysOn') : t('sysOff'))}
          {row(t('sysLastTracking'), dt(info.last_tracking_sync))}
          {row(t('sysLastAis'), dt(info.last_ais_seen))}
          {row(t('sysLastPoImport'), dt(info.last_po_import))}
          {row(t('sysLastContainer'), dt(info.last_container_created))}
          {row(t('sysClientErrors'), String(info.client_errors_24h))}
          {row(t('sysUploadsSize'), `${info.uploads_size_mb} MB`)}
        </dl>
      )}
      <MonitorTabs />
      {integrations && (
        <div className="panel" style={{ marginTop: 16 }}>
          <h3>{t('sysIntegrationsTitle')}</h3>
          <dl style={{ display: 'grid', gridTemplateColumns: 'max-content max-content 1fr', gap: '4px 16px', margin: 0, alignItems: 'center' }}>
            {integrations.map(i => (
              <div key={i.key} style={{ display: 'contents' }}>
                <dt style={{ color: 'var(--muted)' }}>{i.label}</dt>
                <dd style={{ margin: 0 }}>
                  <span className={`badge ${i.status === 'on' ? 'ok' : ''}`}>
                    {i.status === 'on' ? t('sysIntOn') : t('sysIntOff')}
                  </span>
                </dd>
                <dd style={{ margin: 0, color: 'var(--muted)', fontSize: 14 }}>
                  {i.detail}{i.last_signal && ` · ${dt(i.last_signal)}`}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      <div className="panel" style={{ marginTop: 16 }}>
        <h3>{t('sysBackupTitle')}</h3>
        {verify ? (
          <p>
            <b>{verify.status}</b> — {verify.detail}
            {verify.dump && <> · {verify.dump}</>}
            {verify.tables != null && <> · {verify.tables} {t('sysBackupTables')}</>}
            {verify.started_at && <> · {dt(verify.started_at)}</>}
          </p>
        ) : (
          <p className="muted">{t('sysBackupNone')}</p>
        )}
        <button className="btn" disabled={verifying} onClick={runVerify}>
          {verifying ? t('sysBackupRunning') : t('sysBackupRun')}
        </button>
      </div>
    </div>
  )
}
