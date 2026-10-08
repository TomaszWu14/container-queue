// Dokumenty z paczek faktur w szufladzie (audyt 2026-10-06 #20): części zestawu (faktura, PL,
// B/L, certyfikaty) nie były widoczne obok „Plików”, więc wgrywano je drugi raz. Tylko podgląd —
// paczką zarządza sekcja „Faktury (CIPL)” na karcie kontenera. Rola bez dostępu do faktur (403)
// = sekcja niewidoczna.
import { useEffect, useState } from 'react'
import { api, downloadFile, errorMessage } from '../../api'
import { useT } from '../../i18n'
import type { InvoiceBatch } from '../../types'

export function BatchDocuments({ containerId, refreshKey }: { containerId: number; refreshKey?: unknown }) {
  const t = useT()
  const [batches, setBatches] = useState<InvoiceBatch[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    api.get<InvoiceBatch[]>(`/api/containers/${containerId}/invoice-batches`)
      .then(r => setBatches(Array.isArray(r) ? r : [])).catch(() => setBatches([]))
  }, [containerId, refreshKey])
  const jobs = batches.flatMap(b => b.jobs ?? []).filter(j => j.status !== 'uploaded')
  if (!jobs.length) return null
  return (
    <section className="kq-batch-docs" aria-label={t('kqBatchDocs')}>
      <h4>{t('kqBatchDocs')}</h4>
      <ul className="kq-docs">
        {jobs.map(j => (
          <li key={j.id}>
            <i className="kq-doc-ico pdf">PDF</i>
            <div className="kq-doc-main">
              <b title={j.filename}>{j.filename}</b>
              <small>{[t(`invKind_${j.doc_kind}`), t(`invStatus_${j.status}`), j.invoice_number].filter(Boolean).join(' · ')}</small>
            </div>
            <button type="button" className="kq-link"
                    onClick={() => downloadFile(`/api/invoice-jobs/${j.id}/pdf`, j.filename)
                      .catch(err => setError(errorMessage(err)))}>{t('mailPrevOpen')}</button>
          </li>
        ))}
      </ul>
      {error && <p className="error">{error}</p>}
    </section>
  )
}
