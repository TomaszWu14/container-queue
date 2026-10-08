import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import { SapSource } from '../../SapSource'
import ImportModal from '../ImportModal'
import SyncUploadModal from '../SyncUploadModal'
import { TemplateButtons } from '../../importTemplate'
import { useCompanies } from './shared'

// Import z Excela — tylko w panelu admina (schowany przed zwykłymi userami).
export default function ImportTab() {
  const t = useT()
  const companies = useCompanies()
  const [companyCode, setCompanyCode] = useState('')
  const [modal, setModal] = useState<'import' | 'items' | 'etd' | 'sap' | 'sync' | null>(null)
  const close = () => setModal(null)
  // okres dwutorowy Excel ↔ aplikacja: synchronizacja z SharePoint tylko na żądanie (2026-09-28)
  const [spMsg, setSpMsg] = useState('')
  const [spBusy, setSpBusy] = useState(false)
  const syncSharePoint = async () => {
    setSpBusy(true)
    try {
      const r = await api.post<{ status: string }>('/api/import/sharepoint-sync', {})
      setSpMsg(r.status === 'unchanged' ? t('spSyncUnchanged') : t('spSyncDone'))
    } catch (err) { setSpMsg(errorMessage(err)) } finally { setSpBusy(false) }
  }
  return (
    <div className="panel">
      <h3>{t('importExcel')}</h3>
      <p style={{ color: 'var(--muted)', fontSize: 14, margin: '0 0 12px' }}>
        {t('importAdminHint')}
      </p>
      <p style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <button type="button" className="btn small secondary" disabled={spBusy} onClick={syncSharePoint}>
          {t('spSyncNow')}</button>
        <span role="status" className="muted">{spMsg}</span>
      </p>
      <div className="row">
        <select aria-label={t('company')} value={companyCode} onChange={e => setCompanyCode(e.target.value)}>
          <option value="">— {t('company')} —</option>
          {companies.map(c => <option key={c.id} value={c.code}>{c.name}</option>)}
        </select>
        <button className="btn" disabled={!companyCode} onClick={() => setModal('sync')}>
          {t('queueSync')}
        </button>
        <button className="btn secondary" disabled={!companyCode} onClick={() => setModal('import')}>
          {t('importExcel')}
        </button>
        <button className="btn secondary" disabled={!companyCode} onClick={() => setModal('etd')}>
          {t('etdImport')}
        </button>
        <button className="btn secondary" disabled={!companyCode} onClick={() => setModal('sap')}>
          {t('sapOrdersImport')}
        </button>
        <SapSource table="EKKO" />
        <button className="btn secondary" disabled={!companyCode} onClick={() => setModal('items')}>
          {t('importRef')}
        </button>
        <SapSource table="EKPO" />
      </div>
      <div style={{ marginTop: 10 }}><TemplateButtons kinds={['queue', 'etd', 'ekko', 'ref']} /></div>
      {modal === 'import' && (
        <ImportModal companyCode={companyCode} onDone={() => {}} onClose={close} />
      )}
      {modal === 'items' && (
        <ImportModal companyCode={companyCode} endpoint="/api/import/order-items"
                     titleKey="importRef" onDone={() => {}} onClose={close} />
      )}
      {modal === 'etd' && (
        <SyncUploadModal companyCode={companyCode} endpoint="/api/import/purchase-orders"
                         titleKey="etdImport" hintKey="etdImportHint" onDone={() => {}} onClose={close} />
      )}
      {modal === 'sap' && (
        <SyncUploadModal companyCode={companyCode} endpoint="/api/import/sap-orders"
                         titleKey="sapOrdersImport" hintKey="sapOrdersImportHint"
                         onDone={() => {}} onClose={close} />
      )}
      {modal === 'sync' && (
        <SyncUploadModal companyCode={companyCode} endpoint="/api/import/queue-sync"
                         titleKey="queueSync" hintKey="queueSyncHint" onDone={() => {}} onClose={close} />
      )}
    </div>
  )
}
