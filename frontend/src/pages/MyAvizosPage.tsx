// Awizacja w aplikacji (decyzja 2026-10-07: nic bez logowania; przewoźnik = konto spedytora).
// Lista otwartych awizacji spedytora i odpowiedź w tym samym formularzu co dawny link z maila
// (etap 1: termin / slot / problem; etap 2: dane kierowców). Logistyka może odpowiedzieć w imieniu.
import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Inbox } from 'lucide-react'
import { api, errorMessage } from '../api'
import { EmptyState, LoadError, Skeleton } from '../feedback'
import { useT } from '../i18n'
import { formatDateTime } from '../dates'
import { PageHeader } from '../PageHeader'
import AvizoFormPage from './AvizoFormPage'
import AvizoDriverFormPage from './AvizoDriverFormPage'
import { AvizoProposeForm } from './AvizoProposeForm'
import { useToast } from '../feedback'

interface MyAvizo {
  id: number; status: string; stage: number; company: string; forwarder: string
  created_at: string; items: { container_id: number; container_no: string }[]
}

export function MyAvizoAnswer() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const requestId = Number(id)
  return params.get('etap') === '2'
    ? <AvizoDriverFormPage requestId={requestId} />
    : <AvizoFormPage requestId={requestId} />
}

export default function MyAvizosPage() {
  const t = useT()
  const [rows, setRows] = useState<MyAvizo[] | null>(null)
  const [error, setError] = useState('')
  const [proposing, setProposing] = useState<number | null>(null)
  const { showToast } = useToast()

  const load = () => {
    setError('')
    api.get<MyAvizo[]>('/api/avizo-forwarder')
      .then(r => setRows(Array.isArray(r) ? r : []))
      .catch(err => setError(errorMessage(err)))
  }
  useEffect(load, [])

  return (
    <main className="page">
      <PageHeader title={t('myAvizosTitle')} subtitle={t('myAvizosHint')} />
      {error && <LoadError message={error} onRetry={load} />}
      {!rows && !error && <Skeleton rows={3} />}
      {rows && rows.length === 0 && <EmptyState icon={Inbox} title={t('myAvizosNone')} />}
      {rows && rows.length > 0 && (
        <table className="grid">
          <thead><tr><th>#</th><th>{t('company')}</th><th>{t('myAvizosContainers')}</th>
            <th>{t('when')}</th><th></th></tr></thead>
          <tbody>
            {rows.flatMap(r => [
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.company}</td>
                <td className="mono">{r.items.map(i => i.container_no).join(', ')}</td>
                <td>{formatDateTime(r.created_at)}</td>
                <td>
                  {r.stage > 0
                    ? <Link className="btn small" to={`/awizacje/moje/${r.id}?etap=${r.stage}`}>
                        {t(r.stage === 1 ? 'myAvizosConfirm' : 'myAvizosDrivers')}</Link>
                    : <span className="muted">{t('myAvizosWaiting')}</span>}
                  {' '}<button type="button" className="btn small secondary"
                               aria-expanded={proposing === r.id}
                               onClick={() => setProposing(p => p === r.id ? null : r.id)}>
                    {t('myAvizosPropose')}</button>
                </td>
              </tr>,
              proposing === r.id && (
                <tr key={`p-${r.id}`}><td colSpan={5}>
                  <AvizoProposeForm requestId={r.id} items={r.items}
                    onDone={() => { setProposing(null); showToast(t('myAvizosProposed')) }} />
                </td></tr>
              ),
            ])}
          </tbody>
        </table>
      )}
    </main>
  )
}
