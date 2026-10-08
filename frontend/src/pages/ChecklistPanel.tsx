import { TriangleAlertIcon } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api, errorMessage } from '../api'
import { useT } from '../i18n'
import type { ChecklistRow, ChecklistVerdict } from '../types'

// W11 #72: checklista kontroli przyjęcia. Edytowalna na karcie rozładunku
// (editable), tylko do odczytu na karcie kontenera. NOK podpowiada reklamację.
const VERDICTS: ChecklistVerdict[] = ['OK', 'NOK', 'UWAGA']
const VERDICT_BADGE: Record<ChecklistVerdict, string> = {
  OK: 'st-ZREALIZOWANY', NOK: 'st-W_TRANSPORCIE', UWAGA: 'st-ODPRAWA',
}

export function ChecklistPanel({ containerId, editable, framed = false }: {
  containerId: number
  editable: boolean
  framed?: boolean   // true = własna ramka .panel (karta kontenera)
}) {
  const t = useT()
  const [rows, setRows] = useState<ChecklistRow[] | null>(null)
  const [draft, setDraft] = useState<Record<number, { result: ChecklistVerdict | null; note: string }>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  const apply = useCallback((data: ChecklistRow[]) => {
    setRows(data)
    setDraft(Object.fromEntries(data.map(r => [r.point_id, { result: r.result, note: r.note }])))
  }, [])

  useEffect(() => {
    api.get<ChecklistRow[]>(`/api/containers/${containerId}/checklist`)
      .then(apply).catch(() => setRows([]))
  }, [containerId, apply])

  if (!rows) return null
  if (rows.length === 0) {
    // bez punktów: na karcie rozładunku podpowiedz konfigurację, na karcie kontenera nic
    return editable
      ? <section><h3>{t('checklistTitle')}</h3><p className="muted">{t('checklistNone')}</p></section>
      : null
  }
  if (!editable && rows.every(r => !r.result)) return null

  const save = async () => {
    setBusy(true); setError(''); setSaved(false)
    try {
      const items = Object.entries(draft)
        .filter(([, v]) => v.result)
        .map(([pid, v]) => ({ point_id: Number(pid), result: v.result, note: v.note }))
      const data = await api.put<ChecklistRow[]>(`/api/containers/${containerId}/checklist`, { items })
      apply(data)
      setSaved(true)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const anyNok = Object.values(draft).some(v => v.result === 'NOK')

  return (
    <section className={framed ? 'panel checklist-panel' : 'checklist-panel'}>
      <h3>{t('checklistTitle')}</h3>
      {editable && <p className="muted" style={{ fontSize: 14 }}>{t('checklistInfo')}</p>}
      <table className="grid">
        <tbody>
          {rows.map(row => {
            const d = draft[row.point_id] ?? { result: row.result, note: row.note }
            return (
              <tr key={row.point_id}>
                <td>{row.name}</td>
                <td>
                  {editable ? (
                    <div className="row" style={{ gap: 6 }}>
                      {VERDICTS.map(v => (
                        <button key={v} type="button" disabled={busy}
                                className={`btn small ${d.result === v ? '' : 'secondary'}`}
                                onClick={() => setDraft(s => ({ ...s, [row.point_id]: { ...d, result: v } }))}>
                          {v}
                        </button>
                      ))}
                    </div>
                  ) : (
                    row.result
                      ? <span className={`badge ${VERDICT_BADGE[row.result]}`}>{row.result}</span>
                      : <span className="muted">—</span>
                  )}
                </td>
                <td>
                  {editable ? (
                    <input value={d.note} aria-label={t('checklistNote')} placeholder={t('checklistNote')} disabled={busy}
                           onChange={e => setDraft(s => ({ ...s, [row.point_id]: { ...d, note: e.target.value } }))} />
                  ) : (row.note || '')}
                </td>
                {!editable && <td className="muted">{row.checked_by_login ?? ''}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
      {anyNok && <p className="error" style={{ fontSize: 14 }}><TriangleAlertIcon size={14} /> {t('checklistNokHint')}</p>}
      {error && <p className="error">{error}</p>}
      {editable && (
        <div className="row" style={{ marginTop: 8, alignItems: 'center' }}>
          <button className="btn no-print" disabled={busy} onClick={save}>{t('checklistSave')}</button>
          {saved && <span className="muted">✓ {t('checklistSaved')}</span>}
        </div>
      )}
    </section>
  )
}
