import { FlagIcon } from 'lucide-react'
// Pełna karta kontenera (/kontenery/:id) — osobny ekran pod górnym menu aplikacji (2026-09-30):
// pasek „← Kolejka” + ‹ › (gdy weszliśmy z kolejki), nagłówek „czego to dotyczy” wspólny
// z szufladą kolejki, zakładki jak w szufladzie na pełną szerokość. Nic z dawnej karty nie
// zniknęło: panele pracy są w „Szczegółach”, dokumenty/OCR/faktury w „Dokumentach”.
import { useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useSearchParams, useParams } from 'react-router-dom'
import { useUser } from '../App'
import { api, errorMessage } from '../api'
import { LoadError, Skeleton, useToast } from '../feedback'
import { ContainerFormModal, StatusModal, useDicts } from '../components'
import { AttachmentsPanel, MessagesPanel } from '../collaboration'
import { InvoiceBatchesPanel } from '../InvoiceBatchesPanel'
import { AttachmentSuggestionsPanel } from '../DocumentsW5'
import { LangContext, localeFor, useT } from '../i18n'
import type { AuditEntry, Container } from '../types'
import { formatDateTime, formatDayLong } from '../dates'
import { scrollBehavior } from '../motion'
import ContainerSummary from './queue/ContainerSummary'
import { CostsTab, useDrawerData } from './queue/DrawerTabs'
import { FullCardNav } from './queue/fullCard'
import { useWatchReason } from './watch/useWatchReason'
import ContainerActions from './container/ContainerActions'
import ContainerDetails from './container/ContainerDetails'
import DocumentTiles from '../DocumentTiles'
import { IntakePanel } from '../IntakeWaitingRoom'
import './container/fullCard.css'

type Tab = 'details' | 'docs' | 'messages' | 'costs' | 'history'

export default function ContainerPage() {
  const { id } = useParams()
  const [searchParams] = useSearchParams()
  const t = useT()
  const { lang } = useContext(LangContext)
  const user = useUser()
  const dicts = useDicts()
  const { showToast } = useToast()
  const [container, setContainer] = useState<Container | null>(null)
  const [history, setHistory] = useState<AuditEntry[]>([])
  // #33: sugestia statusu z geofence — statek kontenera stoi przy porcie
  const [vesselNearPort, setVesselNearPort] = useState<string>('')
  const [showEdit, setShowEdit] = useState(false)
  const [attachRefresh, setAttachRefresh] = useState(0)
  const [tilesRefresh, setTilesRefresh] = useState(0)
  const [showStatus, setShowStatus] = useState(false)
  const [loadError, setLoadError] = useState('')
  // deep-link z pulpitu: ?akcja=documents otwiera od razu zakładkę Dokumenty
  const akcja = searchParams.get('akcja')
  const [tab, setTab] = useState<Tab>(akcja === 'documents' ? 'docs' : 'details')
  const numericId = Number(id) || 0
  const d = useDrawerData(numericId)   // liczniki zakładek + koszty (jak w szufladzie kolejki)
  const watchReason = useWatchReason(numericId)

  const canEdit = user?.role === 'admin' || user?.role === 'logistics'
  const isWarehouse = user?.role === 'warehouse'
  const isPurchasing = user?.role === 'purchasing'
  const isSales = user?.role === 'sales'

  // po zmianie plików: świeży status kontenera bez zerowania widoku (komunikaty paneli zostają)
  const refreshContainer = useCallback(() => {
    api.get<Container>(`/api/containers/${id}`).then(setContainer).catch(() => {})
  }, [id])
  const loadSeq = useRef(0)
  const load = useCallback(() => {
    // przy zmianie kontenera zerujemy widok i pilnujemy kolejności (bez pokazania cudzych danych)
    const seq = ++loadSeq.current
    setContainer(null)
    setHistory([])
    setLoadError('')
    setVesselNearPort('')
    const containerReq = api.get<Container>(`/api/containers/${id}`)
    containerReq
      .then(c => { if (seq === loadSeq.current) setContainer(c) })
      // chwilowy 5xx nie może cicho wyrzucać usera do /kolejka — pokaż błąd z retry
      .catch(err => { if (seq === loadSeq.current) setLoadError(errorMessage(err)) })
    api.get<AuditEntry[]>(`/api/containers/${id}/history`)
      .then(h => { if (seq === loadSeq.current) setHistory(Array.isArray(h) ? h : []) }).catch(() => {})
    // statek dopasowujemy do TEGO kontenera (z odpowiedzi), nie do stanu — vessels potrafi
    // wrócić pierwsze i wtedy stan jest pusty albo należy do poprzedniego kontenera
    Promise.all([containerReq, api.get<{ name: string; near_port: string }[]>('/api/tracking/vessels')])
      .then(([c, vs]) => {
        if (seq !== loadSeq.current || !Array.isArray(vs)) return
        const own = (c.vessel ?? '').toUpperCase().replace(/-/g, ' ').split(/\s+/).join(' ')
        const hit = vs.find(v => v.name === own && v.near_port)
        setVesselNearPort(hit?.near_port ?? '')
      }).catch(() => {})
  }, [id])

  useEffect(() => load(), [load])

  // deep-link z pulpitu: ?akcja=documents|avizo-form → przewiń do panelu i podświetl
  useEffect(() => {
    if (!container || !akcja) return
    const anchor = akcja === 'documents' ? 'akcja-documents'
      : akcja === 'avizo-form' ? 'akcja-avizo' : null
    if (!anchor) return
    const el = document.getElementById(anchor)
    if (!el) return
    el.scrollIntoView({ behavior: scrollBehavior(), block: 'center' })
    el.classList.add('deep-target')
    const timer = setTimeout(() => el.classList.remove('deep-target'), 2200)
    return () => clearTimeout(timer)
  }, [container, akcja])

  const nav = <FullCardNav id={numericId} />
  if (loadError && !container) return (
    <main className="page">{nav}<LoadError message={loadError} onRetry={load} /></main>
  )
  if (!container) return <main className="page">{nav}<Skeleton rows={6} /></main>

  const fieldLabel = (f: string) => { const k = 'histField_' + f; const v = t(k); return v === k ? f : v }
  const valLabel = (field: string, v: string | null) => {
    if (v === null || v === undefined || v === '' || field !== 'status') return v
    const k = 'st_' + v; const tv = t(k); return tv === k ? v : tv
  }
  // „czego to dotyczy”: spółka · magazyn · dostawa (z dniem tygodnia)
  const meta = [
    container.company_name,
    container.warehouse_name,
    container.notify_date && `${t('kqColDelivery')}: ${formatDayLong(container.notify_date, localeFor(lang))}`,
  ].filter(Boolean).join(' · ')

  // zakładki jak w szufladzie; dokumenty/wiadomości zamknięte dla sprzedaży (jak dawna karta),
  // koszty tylko dla ról z dostępem do faktur frachtowych (403 → brak zakładki)
  const tabs: [Tab, string, number | null | undefined][] = [
    ['details', t('details'), undefined],
    ...(isSales ? [] : [
      ['docs', t('kqdDocs'), d.files?.length ?? null] as [Tab, string, number | null],
      ['messages', t('messages'), d.messages?.length ?? null] as [Tab, string, number | null],
    ]),
    ...(d.costs === 'forbidden' ? [] : [['costs', t('kqdCosts'), undefined] as [Tab, string, undefined]]),
    ['history', t('kqdHistory'), history.length],
  ]
  const pick = (next: Tab) => { setTab(next); d.loadFiles(); d.loadMessages() }   // świeże liczniki

  return (
    <main className="page ct-page">
      {nav}
      <header className="panel ct-head">
        <div className="ct-head-main">
          <div className="ct-head-id">
            <ContainerSummary c={container} watchReason={watchReason} heading
              meta={meta ? <div className="kq-dr-sub">{meta}</div> : undefined}
              badges={<>
                {container.is_special && (
                  <span className="badge special" title={container.special_note || t('specialFlag')}>
                    <FlagIcon size={14} /> {container.special_reason ? t(`reason_${container.special_reason}`) : t('specialFlag')}
                  </span>
                )}
                {container.is_stuck && <span className="badge stuck" title={t('stuckHint')}>{t('stuck')}</span>}
              </>} />
          </div>
          <ContainerActions container={container} setContainer={setContainer}
            onStatus={() => setShowStatus(true)} onEdit={() => setShowEdit(true)} />
        </div>
      </header>

      <div className="kq-dr-tabs ct-tabs" role="tablist" aria-label={t('fcTabs')}>
        {tabs.map(([key, label, n]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key}
                  className={tab === key ? 'active' : ''} onClick={() => pick(key)}>
            {label}{n !== undefined && <> <span className="kq-tab-n mono">{n ?? '…'}</span></>}
          </button>
        ))}
      </div>

      <div role="tabpanel" className="ct-tabpanel">
        {tab === 'details' && (
          <ContainerDetails container={container} setContainer={setContainer} load={load}
            vesselNearPort={vesselNearPort} />
        )}
        {tab === 'docs' && (
          <div className="ct-docs">
            {/* W5 #31: propozycje podpięcia dokumentów z OCR; akceptacja odświeża załączniki (remount) */}
            {(canEdit || isPurchasing) && (
              <AttachmentSuggestionsPanel container={container}
                onAccepted={() => setAttachRefresh(k => k + 1)} />
            )}
            {/* poczekalnia (spec 2026-10-06 §3): „Dodaj dokumenty” → „Sprawdź i potwierdź”; potwierdzenie
                odświeża kafelki, załączniki i status (jedyne wejście nowych plików) */}
            <IntakePanel containerId={container.id}
              onChanged={() => { setTilesRefresh(k => k + 1); setAttachRefresh(k => k + 1); refreshContainer(); d.loadFiles() }} />
            {/* kafelki dokumentów dostawy (spec 2026-10-01): tylko stan + otwarcie pliku */}
            <DocumentTiles key={`tiles-${tilesRefresh}`} containerId={container.id} />
            {/* §4 pkt 29: zmiana plików odświeża status kontenera (ZALACZONE/BRAK) i kafelki */}
            <div id="akcja-documents"><AttachmentsPanel key={attachRefresh} container={container}
              onChanged={() => { setTilesRefresh(k => k + 1); refreshContainer() }} /></div>
            {(canEdit || isPurchasing) && <InvoiceBatchesPanel key={`inv-${attachRefresh}`} container={container}
              onChanged={() => setTilesRefresh(k => k + 1)} />}
          </div>
        )}
        {tab === 'messages' && <MessagesPanel container={container} />}
        {tab === 'costs' && (
          <div className="panel">{Array.isArray(d.costs) ? <CostsTab rows={d.costs} /> : <span className="kq-dim">…</span>}</div>
        )}
        {tab === 'history' && (
          <div className="panel">
            <h3>{t('history')}</h3>
            <div style={{ overflowX: 'auto' }}>
              <table className="grid">
                <thead>
                  <tr>
                    <th>{t('when')}</th>
                    <th>{t('who')}</th>
                    <th>{t('field')}</th>
                    <th>{t('oldValue')}</th>
                    <th>{t('newValue')}</th>
                    <th>{t('notes')}</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map(entry => (
                    <tr key={entry.id}>
                      <td>{formatDateTime(entry.created_at)}</td>
                      <td>{entry.user_login}</td>
                      <td>{fieldLabel(entry.field)}</td>
                      <td>{valLabel(entry.field, entry.old_value)}</td>
                      <td>{valLabel(entry.field, entry.new_value)}</td>
                      <td>{entry.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {showEdit && (
        <ContainerFormModal dicts={dicts} initial={container}
                            onSaved={() => load()} onClose={() => setShowEdit(false)} />
      )}
      {showStatus && (
        <StatusModal container={container} warehouseRole={isWarehouse}
                     onSaved={() => { load(); showToast(t('toastStatusChanged')) }}
                     onClose={() => setShowStatus(false)} />
      )}
    </main>
  )
}
