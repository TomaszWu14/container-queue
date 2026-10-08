// Okno „Porównaj” draftu SAD z paczką faktur (spec 2026-09-29-agencja-draft-sad §2, PR 2):
// nagłówek (faktury, waluta, suma, kraj), grupy CN nasze ↔ SAD, strony PDF obok jako obrazki
// (CSP blokuje iframe/object — backend renderuje strony do PNG).
import { useEffect, useRef, useState } from 'react'
import { CheckIcon, TriangleAlertIcon } from 'lucide-react'
import { api, errorMessage } from './api'
import { Modal } from './components'
import { formatNum } from './dates'
import { useT } from './i18n'
import type { SadComparison, SadDraft, SadField, SadGroup, SadHeaderRow } from './types'
import './SadCompareModal.css'

const STATUS_CLASS: Record<SadGroup['status'], string> = {
  ok: 'badge-ok', diff: 'badge-danger', missing_in_sad: 'badge-danger', extra_in_sad: 'badge-danger', manual: '',
}

function Verdict({ ok, t }: { ok: boolean | null; t: (key: string) => string }) {
  if (ok === true) return <span className="sad-ok" role="img" aria-label={t('sadVerdictOk')}><CheckIcon size={14} /></span>
  if (ok === false) return <span className="sad-warn" role="img" aria-label={t('sadVerdictBad')}><TriangleAlertIcon size={14} /></span>
  return <span className="muted" title={t('sadVerdictManual')}>?</span>
}

// formatNum dopiero po otwarciu okna — sekcja „Agencja” renderuje się też w testach z mockiem ./dates
const pct = (d: number | null) => (d ? ` (${formatNum(d, 2)}%)` : '')
const pair = (f: SadField) => `${formatNum(f.ours)} / ${formatNum(f.sad)}${pct(f.diff_pct)}`
// suma faktur i koszty dodatkowe to liczby; faktury, waluta i kraj — tekst
const headVal = (h: SadHeaderRow, v: string | null) => (h.field === 'total' ? formatNum(v) : v || '—')

export function SadCompareModal({ batchId, draft, onClose, onCompared }: {
  batchId: number
  draft: SadDraft
  onClose: () => void
  onCompared?: () => void
}) {
  const t = useT()
  const base = `/api/invoice-batches/${batchId}/sad-drafts/${draft.id}`
  const [data, setData] = useState<SadComparison | null>(null)
  const [error, setError] = useState('')
  // callback rodzica w refie: nowa funkcja przy każdym renderze rodzica nie może ponawiać POST
  const compared = useRef(onCompared)
  useEffect(() => { compared.current = onCompared })

  useEffect(() => {
    let alive = true
    api.post<SadComparison>(`${base}/compare`, {})
      .then(res => { if (alive) { setData(res); compared.current?.() } })
      .catch(err => { if (alive) setError(errorMessage(err)) })
    return () => { alive = false }
  }, [base])

  const unread = data?.unread.map(u => t(`sadField_${u.field}`) + (u.item ? ` (${t('sadItem')} ${u.item})` : '')) ?? []
  return (
    <Modal title={t('sadCompareTitle').replace('{v}', String(draft.version))} onClose={onClose} width={1240}>
      {error && <p className="error">{error}</p>}
      {!data && !error && <p className="muted" role="status">{t('loading')}</p>}
      {data && (
        <div className="sad-compare">
          <div>
            {data.error && <p className="error">{t(`sadErr_${data.error}`)}</p>}
            <ul className="sad-head">
              {data.header.map(h => (
                <li key={h.field}>
                  <Verdict ok={h.ok} t={t} /> <b>{t(`sadField_${h.field}`)}</b>: {headVal(h, h.ours)} / {headVal(h, h.sad)}{pct(h.diff_pct)}
                  {h.detail && <span className="muted"> · {t(`sadDetail_${h.field}`).replace('{v}', headVal(h, h.detail))}</span>}
                </li>
              ))}
            </ul>
            <div className="sad-table">
              <table className="grid">
                <thead>
                  <tr>
                    <th>{t('sadColCn')}</th><th className="num">{t('sadColValue')}</th><th className="num">{t('sadColMass')}</th>
                    <th className="num">{t('sadColSuppl')}</th><th>{t('sadColStatus')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.groups.map(g => (
                    <tr key={g.cn}>
                      <td className="mono" title={g.refs.join(', ')}>{g.cn}</td>
                      <td className="num">{pair(g.value)}</td>
                      <td className="num">{pair(g.net_mass)}</td>
                      <td className="num">{g.suppl_qty ? `${pair(g.suppl_qty)} ${g.suppl_unit}` : '—'}</td>
                      <td><span className={`badge ${STATUS_CLASS[g.status] ?? ''}`}>{t(`sadStatus_${g.status}`)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {unread.length > 0 && <p className="muted">{t('sadUnread').replace('{list}', unread.join(', '))}</p>}
            {data.no_cn.length > 0 && <p className="muted">{t('sadNoCn').replace('{list}', data.no_cn.join(', '))}</p>}
            <p className="muted">
              {t('sadTolerance').replace('{a}', formatNum(data.tolerances.amount_pct))
                .replace('{q}', formatNum(data.tolerances.qty_pct)).replace('{kg}', formatNum(data.tolerances.mass_abs_kg))}
            </p>
          </div>
          <div className="sad-pages">
            {Array.from({ length: data.pages }, (_, i) => (
              <img key={i} src={`${base}/pages/${i + 1}`} alt={`${t('sadPage')} ${i + 1}`}
                   width={420} height={594} loading="lazy" decoding="async" />
            ))}
          </div>
        </div>
      )}
    </Modal>
  )
}
