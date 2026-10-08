import { BotIcon } from 'lucide-react'
// Asystent wiedzy (#38): pytanie → fakty z bazy (kontenery/materiały) → odpowiedź
// lokalnego modelu (Ollama na własnym serwerze). Bez modelu pokazujemy same fakty.
import { Fragment, useState } from 'react'
import { api, errorMessage } from './api'
import { useT } from './i18n'

type Facts = { kontenery: Record<string, unknown>[]; materialy: Record<string, unknown>[] }
type AskOut = { answer: string | null; facts: Facts; ai: boolean }

function FactList({ title, rows }: { title: string; rows: Record<string, unknown>[] }) {
  if (!rows.length) return null
  return (
    <div style={{ marginTop: 8 }}>
      <b style={{ fontSize: 13 }}>{title}</b>
      {rows.map((row, i) => (
        <dl key={i} data-testid="as-fact" style={{
          display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '2px 8px', margin: '4px 0',
          fontSize: 13, padding: '6px 8px', borderRadius: 6,
          border: '1px solid var(--border, #dde3ec)',
        }}>
          {Object.entries(row).filter(([, v]) => v !== null && v !== '').map(([k, v]) => (
            <Fragment key={k}><dt className="muted">{k}</dt><dd style={{ margin: 0 }}>{String(v)}</dd></Fragment>
          ))}
        </dl>
      ))}
    </div>
  )
}

export default function AssistantBox() {
  const t = useT()
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState<AskOut | null>(null)
  const [error, setError] = useState('')

  const ask = async (e: React.FormEvent) => {
    e.preventDefault()
    if (question.trim().length < 2 || busy) return
    setBusy(true); setError('')
    try {
      setOut(await api.post<AskOut>('/api/assistant/ask', { question: question.trim() }))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const empty = out && !out.facts.kontenery.length && !out.facts.materialy.length
  return (
    <section style={{ marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border, #dde3ec)' }}>
      <h4 style={{ margin: '0 0 6px' }}><BotIcon size="1em" /> {t('asTitle')}</h4>
      <form onSubmit={ask} style={{ display: 'flex', gap: 6 }}>
        <input value={question} onChange={e => setQuestion(e.target.value)} maxLength={500}
               placeholder={t('asPlaceholder')} aria-label={t('asTitle')} style={{ flex: 1 }} />
        <button className="btn small" disabled={busy}>{t('asAsk')}</button>
      </form>
      {busy && <p className="muted" style={{ fontSize: 13 }}>{t('asThinking')}</p>}
      {error && <p role="alert" style={{ color: 'var(--danger, #b42318)', fontSize: 13 }}>{error}</p>}
      {out && !busy && (
        <div aria-live="polite">
          {out.answer && <p style={{ margin: '8px 0', whiteSpace: 'pre-wrap' }}>{out.answer}</p>}
          {empty && <p className="muted" style={{ fontSize: 13 }}>{t('asNoFacts')}</p>}
          {!out.ai && !empty && <p className="muted" style={{ fontSize: 12 }}>{t('asNoAi')}</p>}
          <FactList title={t('asContainers')} rows={out.facts.kontenery} />
          <FactList title={t('asMaterials')} rows={out.facts.materialy} />
        </div>
      )}
    </section>
  )
}
