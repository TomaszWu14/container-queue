// #41 — archiwum dokumentów z wyszukiwaniem pełnotekstowym po wszystkich źródłach
// (załączniki kontenerów, dokumenty faktur, faktury transportowe) w zasięgu spółki.
import { useState } from 'react'
import { api, downloadFile, errorMessage } from '../../api'
import { useT } from '../../i18n'

interface DocResult {
  source: string
  id: number
  title: string
  container_id: number | null
  container_no: string | null
  supplier_name: string | null
  document_type: string | null
  created_at: string | null
  download_url: string | null
}

const SOURCE_LABEL: Record<string, string> = {
  attachment: 'Załącznik', invoice: 'Faktura', freight: 'Fracht',
}

export default function DocumentsSearchTab() {
  const t = useT()
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<DocResult[] | null>(null)
  const [error, setError] = useState('')

  const search = () => {
    setError('')
    api.get<DocResult[]>(`/api/documents/search?q=${encodeURIComponent(q.trim())}`)
      .then(r => setRows(Array.isArray(r) ? r : []))
      .catch(e => { setError(errorMessage(e)); setRows([]) })
  }

  return (
    <div className="panel">
      <h3>{t('docSearchTitle')}</h3>
      <div className="row" style={{ marginBottom: 12 }}>
        <input value={q} aria-label={t('docSearchPlaceholder')} placeholder={t('docSearchPlaceholder')} style={{ minWidth: 260 }}
               onChange={e => setQ(e.target.value)}
               onKeyDown={e => { if (e.key === 'Enter') search() }} />
        <button className="btn" onClick={search}>{t('search')}</button>
      </div>
      {error && <p className="error">{error}</p>}
      {rows && rows.length === 0 && <p className="muted">{t('docSearchEmpty')}</p>}
      {rows && rows.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="grid">
            <thead>
              <tr>
                <th>{t('docSearchDoc')}</th><th>{t('containerNo')}</th>
                <th>{t('supplier')}</th><th>{t('docSearchType')}</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={`${r.source}-${r.id}`}>
                  <td>{r.title}
                    <div className="muted" style={{ fontSize: 11 }}>
                      {SOURCE_LABEL[r.source] ?? r.source}
                    </div>
                  </td>
                  <td className="mono">{r.container_no ?? '—'}</td>
                  <td>{r.supplier_name ?? '—'}</td>
                  <td>{r.document_type ?? '—'}</td>
                  <td>{r.download_url && (
                    <button className="btn small secondary"
                            onClick={() => downloadFile(r.download_url!, r.title)
                              .catch(e => setError(errorMessage(e)))}>
                      {t('download')}
                    </button>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
