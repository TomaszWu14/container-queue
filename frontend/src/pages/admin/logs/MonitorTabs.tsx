// Podzakładki Monitora serwera: Zasoby (istniejący MonitorPanel) + dziennik żądań/zadań/błędów.
// Każda podzakładka montuje (i ładuje dane) dopiero po otwarciu.
import { useState } from 'react'
import { useT } from '../../../i18n'
import MonitorPanel from '../MonitorPanel'
import LogsRequests from './LogsRequests'
import LogsJobs from './LogsJobs'
import LogsClientErrors from './LogsClientErrors'

type TabKey = 'resources' | 'requests' | 'jobs' | 'clientErrors'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'resources', label: 'logTabResources' },
  { key: 'requests', label: 'logTabRequests' },
  { key: 'jobs', label: 'logTabJobs' },
  { key: 'clientErrors', label: 'logTabClientErrors' },
]

export default function MonitorTabs() {
  const t = useT()
  const [active, setActive] = useState<TabKey>('resources')

  return (
    <div style={{ marginTop: 16 }}>
      <div className="log-tabs">
        {TABS.map(tab => (
          <button key={tab.key} type="button"
                  className={`btn small${active === tab.key ? '' : ' secondary'}`}
                  onClick={() => setActive(tab.key)}>
            {t(tab.label)}
          </button>
        ))}
      </div>
      {active === 'resources' && <MonitorPanel />}
      {active === 'requests' && <div className="panel"><LogsRequests /></div>}
      {active === 'jobs' && <div className="panel"><LogsJobs /></div>}
      {active === 'clientErrors' && <div className="panel"><LogsClientErrors /></div>}
    </div>
  )
}
