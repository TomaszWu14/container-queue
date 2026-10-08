// Dziennik błędów frontu (admin) — tabela z rozwijanym stack trace
import { Fragment, useEffect, useState } from 'react'
import { api, errorMessage } from '../../../api'
import { useT } from '../../../i18n'
import { formatDateTime } from '../../../dates'

interface ClientErrorRow {
  id: number; created_at: string; name: string; message: string
  stack: string | null; url: string; user_agent: string
}

export default function LogsClientErrors() {
  const t = useT()
  const [items, setItems] = useState<ClientErrorRow[]>([])
  const [error, setError] = useState('')
  const [openId, setOpenId] = useState<number | null>(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let live = true
    api.get<ClientErrorRow[]>('/api/admin/logs/client-errors')
      .then(r => { if (live) { setItems(Array.isArray(r) ? r : []); setError('') } })
      .catch(err => { if (live) setError(errorMessage(err)) })
    return () => { live = false }
  }, [nonce])

  return (
    <div>
      {error && <p className="error">{error}</p>}
      <div className="log-toolbar">
        <button type="button" className="btn small secondary" onClick={() => setNonce(n => n + 1)}>
          {t('logRefresh')}
        </button>
      </div>
      {items.length === 0 ? <p className="muted">{t('logEmpty')}</p> : (
        <table className="grid">
          <thead>
            <tr>
              <th>{t('logClientErrColAt')}</th><th>{t('logClientErrColName')}</th>
              <th>{t('logClientErrColMessage')}</th><th>{t('logClientErrColUrl')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map(e => (
              <Fragment key={e.id}>
                <tr className="clickable" onClick={() => setOpenId(openId === e.id ? null : e.id)}>
                  <td className="mono">{formatDateTime(e.created_at)}</td>
                  <td>{e.name}</td>
                  <td>{e.message}</td>
                  <td className="mono">{e.url}</td>
                </tr>
                {openId === e.id && (
                  <tr><td colSpan={4}><pre>{e.stack || t('logNoDetails')}</pre></td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
