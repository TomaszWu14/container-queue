import { CircleCheckIcon } from 'lucide-react'
// Publiczny formularz awizacji — ETAP 1 (potwierdzenie dostaw). Dostęp po jednorazowym
// tokenie z e-maila, bez logowania. Per kontener: potwierdzam / zmiana terminu (+slot) /
// problem. Dane kierowców zbiera osobny formularz etapu 2 (AvizoDriverFormPage).
// Kontrakt: backend/app/routers/avizo.py — 404 nieznany, 410 wygasły/unieważniony,
// 409 już wysłany (bez danych), 422 walidacja, 429 limit.
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { detailMessage, errorMessage } from '../api'
import { CSRF_HEADERS } from '../csrf'
import { useT } from '../i18n'
import { formatDate } from '../dates'
import { LoadError, Skeleton } from '../feedback'

type Slot = { time: string; free: number }
type Decision = 'confirmed' | 'date_change' | 'problem'

export interface AvizoHead {
  language: string
  forwarder: string
  company: string
  note: string
}

interface Stage1Item {
  container_id: number
  container_no: string
  vessel: string
  notify_date: string | null
  warehouse: string
  slot_time: string | null
  slots: Slot[]   // wolne okna na dzień awizacji (pusta lista = magazyn bez slotów)
}

interface Stage1Data extends AvizoHead {
  reject_comment: string
  items: Stage1Item[]
}

interface Answer {
  decision: Decision
  proposed_date: string
  slot_time: string
  comment: string
  slots: Slot[]   // sloty dla aktualnie wybranego dnia
}

export type FormState<T> =
  | { kind: 'loading' } | { kind: 'gone' } | { kind: 'done' }
  | { kind: 'error'; message: string } | { kind: 'ready'; data: T }

// wspólne dla etapu 1 i 2: GET po tokenie z rozróżnieniem 404/410 (link martwy),
// 409 (już wysłany) i 5xx/sieć (retry — nie fałszywe „nie istnieje")
export function usePublicForm<T>(url: string) {
  const [state, setState] = useState<FormState<T>>({ kind: 'loading' })
  const load = useCallback(async () => {
    setState({ kind: 'loading' })
    try {
      const response = await fetch(url)
      if (response.ok) setState({ kind: 'ready', data: await response.json() })
      else if (response.status === 404 || response.status === 410) setState({ kind: 'gone' })
      else if (response.status === 409) setState({ kind: 'done' })
      else setState({ kind: 'error', message: `Błąd ${response.status}` })
    } catch (err) {
      setState({ kind: 'error', message: errorMessage(err) })
    }
  }, [url])
  useEffect(() => { void load() }, [load])
  return { state, setState, load }
}

// POST JSON (backend wymaga application/json — ochrona przed formularzem z obcej strony)
export async function postPublic(url: string, body: unknown):
    Promise<{ ok: true } | { ok: false; status: number; message: string; code?: string }> {
  const response = await fetch(url, {
    method: 'POST', headers: { ...CSRF_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (response.ok) return { ok: true }
  const payload = await response.json().catch(() => ({}))
  return { ok: false, status: response.status, code: payload.detail?.code,
           message: detailMessage(payload.detail, `Błąd ${response.status}`) }
}

// ramka strony publicznej — nagłówek + stany końcowe wspólne dla obu etapów
export function PublicShell<T extends AvizoHead>({ state, load, title, lang, doneText, children }: {
  state: FormState<T>
  load: () => void
  title: string
  lang?: string
  doneText: string
  children: (data: T) => ReactNode
}) {
  const t = useT(lang)
  const head = state.kind === 'ready' ? state.data : null
  return (
    <main className="page avizo-page">
      <header className="avizo-head">
        <span className="brand-dark">KOLEJKA</span>
        <h1>{title}</h1>
        {head && (
          <p>
            {t('forwarder')}: <b>{head.forwarder}</b>
            {head.company && <span className="muted"> · {head.company}</span>}
          </p>
        )}
        {head?.note && <p className="muted">{t('notes')}: {head.note}</p>}
      </header>
      {state.kind === 'loading' && <Skeleton rows={4} />}
      {state.kind === 'error' && <LoadError message={state.message} onRetry={load} />}
      {state.kind === 'gone' && <div className="panel"><p>{t('avizoNotFound')}</p></div>}
      {state.kind === 'done' && (
        <div className="panel avizo-thanks">
          <h2><CircleCheckIcon size="1em" /> {t('av1Done')}</h2>
          <p>{doneText}</p>
        </div>
      )}
      {state.kind === 'ready' && children(state.data)}
    </main>
  )
}

// requestId = awizacja w aplikacji (spedytor z kontem, 2026-10-07) — te same reguły co link z maila
export default function AvizoFormPage({ requestId }: { requestId?: number } = {}) {
  const { token } = useParams()
  const base = requestId ? `/api/avizo-forwarder/${requestId}` : `/api/avizo/${token}`
  const { state, setState, load } = usePublicForm<Stage1Data>(base)
  const lang = state.kind === 'ready' ? state.data.language : undefined
  const t = useT(lang)
  const [answers, setAnswers] = useState<Record<number, Answer>>({})
  const [touched, setTouched] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // odpowiedź domyślna liczona z pozycji (nie w useEffect) — klik „Wyślij” tuż po
  // wyrenderowaniu formularza nie trafia już w pusty stan (TypeError → fałszywy błąd)
  const initial = (i: Stage1Item): Answer => ({
    decision: 'confirmed', proposed_date: '', slot_time: i.slot_time ?? '', comment: '',
    slots: i.slots ?? [],
  })
  const answerOf = (i: Stage1Item) => answers[i.container_id] ?? initial(i)

  const patch = (item: Stage1Item, p: Partial<Answer>) =>
    setAnswers(all => ({ ...all, [item.container_id]: { ...(all[item.container_id] ?? initial(item)), ...p } }))

  const choose = (item: Stage1Item, decision: Decision) =>
    patch(item, decision === 'date_change'
      ? { decision, slot_time: '', slots: [] }   // sloty dopiero po wyborze nowego dnia
      : { decision, proposed_date: '', slot_time: item.slot_time ?? '', slots: item.slots ?? [] })

  // zmiana daty → świeża lista wolnych slotów tego dnia (wybrany slot może już nie pasować)
  const changeDate = async (item: Stage1Item, date: string) => {
    patch(item, { proposed_date: date, slot_time: '', slots: [] })
    if (!date || !item.slots?.length) return
    try {
      const r = await fetch(`${base}/slots?container_id=${item.container_id}&date=${date}`)
      if (r.ok) patch(item, { slots: await r.json() })
    } catch { /* bez sieci brak listy — backend i tak odrzuci zajęty slot (409) */ }
  }

  const invalid = (a: Answer | undefined) => !a ? '' :
    a.decision === 'date_change' && !a.proposed_date ? t('av1DateRequired')
      : a.decision === 'problem' && !a.comment.trim() ? t('av1ProblemRequired') : ''

  const submit = async (items: Stage1Item[]) => {
    setTouched(true)
    setError('')
    if (items.some(i => invalid(answerOf(i)))) return
    setBusy(true)
    try {
      const res = await postPublic(requestId ? `${base}/confirm` : base, {
        items: items.map(i => {
          const a = answerOf(i)
          return {
            container_id: i.container_id, decision: a.decision,
            proposed_date: a.decision === 'date_change' ? a.proposed_date : null,
            slot_time: a.decision === 'problem' ? '' : a.slot_time,
            comment: a.comment.trim(),
          }
        }),
      })
      if (res.ok) setState({ kind: 'done' })
      else if (res.status === 410) setState({ kind: 'gone' })
      // 409 slot_taken to błąd do poprawy, nie koniec formularza (already_submitted = koniec)
      else if (res.status === 409 && res.code !== 'slot_taken') setState({ kind: 'done' })
      else setError(res.message)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <PublicShell state={state} load={load} lang={lang} title={t('av1Title')}
                 doneText={t('av1DoneInfo')}>
      {data => (
        <>
          <p className="muted">{t('av1Intro')}</p>
          {data.reject_comment && (
            <p className="error"><b>{t('av1RejectedPrev')}:</b> {data.reject_comment}</p>
          )}
          {data.items.map(item => {
            const a = answerOf(item)
            const msg = touched ? invalid(a) : ''
            const name = `decision-${item.container_id}`
            return (
              <section key={item.container_id} className="panel avizo-card">
                <div className="avizo-card-head">
                  <b className="mono">{item.container_no}</b>
                  <span className="muted">
                    {[item.vessel, item.warehouse].filter(Boolean).join(' · ')}
                  </span>
                  <span className="mono">{formatDate(item.notify_date)}
                    {item.slot_time && ` ${item.slot_time}`}</span>
                </div>
                <div className="avizo-choice" role="radiogroup" aria-label={item.container_no}>
                  {(['confirmed', 'date_change', 'problem'] as const).map(d => (
                    <label key={d}>
                      <input type="radio" name={name} checked={a.decision === d}
                             onChange={() => choose(item, d)} />
                      {t(d === 'confirmed' ? 'av1Confirm' : d === 'date_change' ? 'av1DateChange' : 'av1Problem')}
                    </label>
                  ))}
                </div>
                <div className="avizo-fields">
                  {a.decision === 'date_change' && (
                    <label>{t('av1NewDate')}
                      <input type="date" value={a.proposed_date}
                             onChange={e => void changeDate(item, e.target.value)} />
                    </label>
                  )}
                  {a.decision !== 'problem' && a.slots.length > 0 && (
                    <label>{t('avizoSlot')}
                      <select value={a.slot_time}
                              onChange={e => patch(item, { slot_time: e.target.value })}>
                        <option value="">—</option>
                        {a.slots.map(s => (
                          <option key={s.time} value={s.time}
                                  disabled={s.free <= 0 && s.time !== item.slot_time}>
                            {s.time}{s.free <= 0 ? ` · ${t('avizoSlotFull')}` : ''}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <label className="avizo-wide">{t('av1Comment')}
                    <textarea rows={2} maxLength={1000} value={a.comment}
                              onChange={e => patch(item, { comment: e.target.value })} />
                  </label>
                </div>
                {msg && <p className="error">{msg}</p>}
              </section>
            )
          })}
          {error && <p className="error">{error}</p>}
          <div className="row" style={{ justifyContent: 'flex-end', marginTop: 14 }}>
            <button className="btn" disabled={busy} onClick={() => void submit(data.items)}>
              {busy ? t('loading') : t('av1Submit')}
            </button>
          </div>
        </>
      )}
    </PublicShell>
  )
}
