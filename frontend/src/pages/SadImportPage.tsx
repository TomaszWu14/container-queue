// Import SAD: podglądy zgłoszeń z WinSAD (PDF) → sprawdzenie (nagłówek, pozycje, walidacja
// rachunkowa i formalna) oraz raport Excel. Backend: routers/sad_import.py — pliki czytane
// w pamięci, zakres spółek po kontenerze z SAD (plik spoza zakresu = błąd bez danych).
import { useRef, useState } from 'react'
import { Download, FileCheck, Upload } from 'lucide-react'
import { api, downloadFile, errorMessage } from '../api'
import { formatDate, formatNum, todayISO } from '../dates'
import { useT } from '../i18n'
import { PageHeader } from '../PageHeader'

const CHECK_URL = '/api/sad-import/check'
const REPORT_URL = '/api/sad-import/report'
const MAX_FILES = 20
const NUM = { textAlign: 'right', whiteSpace: 'nowrap' } as const   // kolumny kwot

type SadStatus = 'OK' | 'WARN' | 'ERROR'
interface SadFee { podstawa: string | null; stawka: string | null; kwota_nalezna: string | null; metoda: string | null }
interface SadItem {
  nr: number; opis: string; cn: string; taric: string
  wartosc_fakturowa: string | null; masa_netto: string | null; ilosc_uzup: string | null
  faktury: string[]; proformy: string[]; a00: SadFee | null; b00: SadFee | null; kwota_ogolem: string | null
}
interface SadRule { poziom: string; pozycja: number | null; regula: string; oczekiwane: string; odczytane: string; status: SadStatus }
interface SadHeader {
  numer: string; stan_ais: string; data_zgloszenia: string | null; data_wydruku: string | null; lrn: string
  nadawca: string; odbiorca: string; kontenery: string[]; wartosc_faktur: string | null; waluta: string
  kurs: string | null; liczba_pozycji: number | null; liczba_opakowan: number | null; masa_brutto: string | null
  suma_cla: string | null; suma_vat: string | null; status: SadStatus
}
export interface SadFileResult {
  plik: string; ok: boolean; blad: string | null
  zgloszenie: SadHeader | null; pozycje: SadItem[]; wyniki: SadRule[]
}

// WARN: bursztynowa plakietka z tokenów --warning-* (jak „zlecona” w odprawie)
const BADGE: Record<SadStatus, string> = { OK: 'badge-ok', WARN: 'badge cs-ZLECONA', ERROR: 'badge-danger' }

function StatusBadge({ status }: { status: SadStatus }) {
  const t = useT()
  return <span className={BADGE[status]}>{t(`sadImpStatus_${status}`)}</span>
}

function Rules({ rules }: { rules: SadRule[] }) {
  const t = useT()
  const [all, setAll] = useState(false)
  const shown = all ? rules : rules.filter(r => r.status !== 'OK')
  return (
    <>
      <h3>{t('sadImpChecks')}</h3>
      {shown.length ? (
        <table className="grid">
          <thead><tr>
            <th>{t('sadImpItemNo')}</th><th>{t('sadImpRule')}</th><th>{t('sadImpExpected')}</th>
            <th>{t('sadImpRead')}</th><th>{t('sadImpStatus')}</th>
          </tr></thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={i}>
                <td>{r.pozycja ?? '—'}</td><td>{r.regula}</td>
                <td className="mono">{r.oczekiwane}</td><td className="mono">{r.odczytane}</td>
                <td><StatusBadge status={r.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">{t('sadImpAllOk')}</p>}
      <button type="button" className="btn small secondary" aria-pressed={all} onClick={() => setAll(v => !v)}>
        {all ? t('sadImpShowIssues') : t('sadImpShowAll').replace('{n}', String(rules.length))}
      </button>
    </>
  )
}

function Items({ items }: { items: SadItem[] }) {
  const t = useT()
  return (
    <>
      <h3>{t('sadImpItems')}</h3>
      <table className="grid">
        <thead><tr>
          <th>{t('sadImpItemNo')}</th><th>{t('sadImpCn')}</th><th style={NUM}>{t('sadImpItemValue')}</th>
          <th style={NUM}>{t('sadImpA00')}</th><th style={NUM}>{t('sadImpB00')}</th>
        </tr></thead>
        <tbody>
          {items.map(p => (
            <tr key={p.nr}>
              <td>{p.nr}</td><td className="mono" title={p.opis}>{p.cn || '—'}</td>
              <td style={NUM}>{formatNum(p.wartosc_fakturowa, 2)}</td>
              <td style={NUM}>{formatNum(p.a00?.kwota_nalezna)}</td>
              <td style={NUM}>{formatNum(p.b00?.kwota_nalezna)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function SadCard({ result }: { result: SadFileResult }) {
  const t = useT()
  const z = result.zgloszenie
  if (!result.ok || !z) {
    return (
      <section className="panel" aria-label={result.plik}>
        <h2 className="as-h3">{result.plik} <span className="badge-danger">{t('sadImpFileError')}</span></h2>
        <p className="error">{result.blad}</p>
      </section>
    )
  }
  return (
    <section className="panel" aria-label={result.plik}>
      <h2 className="as-h3">{t('sadImpNumber').replace('{n}', z.numer)} <StatusBadge status={z.status} /></h2>
      <p className="muted">{result.plik}</p>
      <div className="detail-grid">
        <div className="item"><b>{t('sadImpLrn')}</b>{z.lrn || '—'}</div>
        <div className="item"><b>{t('sadImpContainers')}</b>{z.kontenery.join(', ') || '—'}</div>
        <div className="item"><b>{t('sadImpInvoiceValue')}</b>{formatNum(z.wartosc_faktur, 2)} {z.waluta}</div>
        <div className="item"><b>{t('sadImpDuty')}</b>{formatNum(z.suma_cla)} PLN</div>
        <div className="item"><b>{t('sadImpVat')}</b>{formatNum(z.suma_vat)} PLN</div>
        <div className="item"><b>{t('sadImpDate')}</b>{formatDate(z.data_zgloszenia)}</div>
        <div className="item"><b>{t('sadImpAis')}</b>{z.stan_ais || '—'}</div>
      </div>
      <Items items={result.pozycje} />
      <Rules rules={result.wyniki} />
    </section>
  )
}

export default function SadImportPage() {
  const t = useT()
  const input = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [results, setResults] = useState<SadFileResult[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const tooMany = files.length > MAX_FILES
  const ready = files.length > 0 && !tooMany && !busy

  const pick = (list: FileList | null) => {
    setFiles(Array.from(list ?? []))
    setResults(null)
    setError('')
  }
  const run = async (action: () => Promise<void>) => {
    setBusy(true)
    setError('')
    try { await action() } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  const check = () => run(async () => {
    setResults((await api.upload<{ files: SadFileResult[] }>(CHECK_URL, files, 'files')).files)
  })
  const report = () => run(async () => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    await downloadFile(REPORT_URL, `sad_raport_${todayISO()}.xlsx`, form)
  })
  const okCount = results?.filter(r => r.ok).length ?? 0

  return (
    <main className="page">
      <PageHeader title={t('sadImpTitle')} subtitle={t('sadImpSubtitle')} />
      <section className="panel">
        <div className="row">
          <input ref={input} type="file" accept=".pdf,application/pdf" multiple hidden
                 aria-label={t('sadImpFiles')}
                 onChange={e => { pick(e.target.files); e.target.value = '' }} />
          <button type="button" className="btn secondary" disabled={busy} onClick={() => input.current?.click()}>
            <Upload size={16} aria-hidden="true" /> {t('sadImpPick')}
          </button>
          <span className="muted" title={files.map(f => f.name).join(', ') || undefined}>
            {files.length ? t('sadImpPicked').replace('{n}', String(files.length)) : t('fileNone')}
          </span>
          <button type="button" className="btn" disabled={!ready} onClick={check}>
            <FileCheck size={16} aria-hidden="true" /> {t('sadImpCheck')}
          </button>
          <button type="button" className="btn secondary" disabled={!ready} onClick={report}>
            <Download size={16} aria-hidden="true" /> {t('sadImpExcel')}
          </button>
        </div>
        <p className="muted">{t('sadImpHint').replace('{max}', String(MAX_FILES))}</p>
        {tooMany && (
          <p className="error">
            {t('sadImpTooMany').replace('{n}', String(files.length)).replace('{max}', String(MAX_FILES))}
          </p>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        {results && (
          <p role="status">
            {t('sadImpSummary').replace('{n}', String(results.length)).replace('{ok}', String(okCount))
              .replace('{bad}', String(results.length - okCount))}
          </p>
        )}
      </section>
      {results?.map((r, i) => <SadCard key={`${i}-${r.plik}`} result={r} />)}
    </main>
  )
}
