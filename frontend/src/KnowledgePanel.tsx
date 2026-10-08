// Panel wiedzy (W16): ikona 📘 z licznikiem + boczny panel z pinezkami wiedzy
// dla podanych kontekstów (ekran / port / dostawca / typ dokumentu / proces).
// YouTube i artykuły pokazujemy jako LINK (CSP blokuje zewnętrzne iframy).
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, errorMessage } from './api'
import AssistantBox from './AssistantBox'
import { useUser } from './App'
import { useT } from './i18n'
import type { KnowledgeBulletin, KnowledgeNote, KnowledgeScope } from './types'
import { BookOpen, HandIcon, LinkIcon, MegaphoneIcon, PencilIcon, PlayIcon, Trash2Icon, X } from 'lucide-react'
import { useConfirm } from './ConfirmDialog'
import { useToast } from './feedback'
import { seesKnowledge, writesKnowledge } from './routing'
import { useBusy } from './useBusy'
import { useVisibleInterval } from './useVisibleInterval'

const EMPTY_FORM = { title: '', body: '', url: '' }

function isYouTube(url: string): boolean {
  return /youtube\.com|youtu\.be/i.test(url)
}

// ACL-001: baza wiedzy bez partnerów zewnętrznych (spedytor, agencja celna) — API i tak 403
export default function KnowledgePanel(props: { scopes: KnowledgeScope[]; variant?: 'topbar' }) {
  const user = useUser()
  if (!seesKnowledge(user?.role)) return null
  return <KnowledgePanelBody {...props} />
}

function KnowledgePanelBody({ scopes, variant }: { scopes: KnowledgeScope[]; variant?: 'topbar' }) {
  const t = useT()
  const { confirm } = useConfirm()
  const user = useUser()
  const canEdit = user?.role === 'admin' || user?.role === 'logistics'
  const { showToast } = useToast()
  const { busy, run } = useBusy()   // dwuklik „Zapisz”/„Wyślij” = jeden wpis
  const [notes, setNotes] = useState<KnowledgeNote[]>([])
  const [open, setOpen] = useState(false)
  // formularze: dodawanie pinezki (edytorzy) i zgłaszanie tematu (wszyscy)
  const [adding, setAdding] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [topicMode, setTopicMode] = useState(false)
  const [topicForm, setTopicForm] = useState({ title: '', body: '' })
  const [sent, setSent] = useState(false)

  const scopeKeyOf = (n: KnowledgeNote) => `${n.scope_type}:${n.scope_key}`
  const wanted = new Set(scopes.map(s => `${s.scope_type}:${s.scope_key}`))

  // numer żądania: po zmianie ekranu (scopes) wolna odpowiedź starego nie nadpisze nowego
  const seq = useRef(0)
  const reload = useCallback(() => {
    const my = ++seq.current
    Promise.all(scopes.map(s =>
      api.get<KnowledgeNote[]>(
        `/api/knowledge/notes?scope_type=${encodeURIComponent(s.scope_type)}`
        + `&scope_key=${encodeURIComponent(s.scope_key)}`).catch(() => [])))
      .then(lists => {
        if (my !== seq.current) return
        const seen = new Set<number>()
        setNotes(lists.flat().filter(n => !seen.has(n.id) && seen.add(n.id) !== undefined))
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(scopes)])

  useEffect(() => { reload() }, [reload])

  useEffect(() => {
    if (!open) return
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onEsc)
    return () => window.removeEventListener('keydown', onEsc)
  }, [open])

  const primary = scopes[0]
  if (!primary) return null

  // błąd zapisu (403, sieć) → toast zamiast cichego unhandled rejection
  const guarded = (fn: () => Promise<void>) => run(() => fn().catch(err => showToast(errorMessage(err), 'error')))

  const saveNote = () => guarded(async () => {
    if (!form.title.trim()) return
    const payload = { ...form, scope_type: primary.scope_type, scope_key: primary.scope_key }
    if (editId != null) await api.patch(`/api/knowledge/notes/${editId}`, payload)
    else await api.post('/api/knowledge/notes', payload)
    setForm(EMPTY_FORM); setAdding(false); setEditId(null)
    reload()
  })

  const removeNote = (id: number) => guarded(async () => {
    if (!(await confirm(t('kbDeleteConfirm'), { danger: true }))) return
    await api.del(`/api/knowledge/notes/${id}`)
    reload()
  })

  const sendTopic = () => guarded(async () => {
    if (!topicForm.title.trim()) return
    await api.post('/api/knowledge/topics', {
      scope_type: primary.scope_type, scope_key: primary.scope_key, ...topicForm,
    })
    setTopicForm({ title: '', body: '' }); setTopicMode(false); setSent(true)
    setTimeout(() => setSent(false), 4000)
  })

  return (
    <>
      {/* w topbarze: przycisk ikonowy na ciemnym tle (design system), w treści: zwykły secondary */}
      <button type="button" className={variant === 'topbar' ? 'tn-icon-btn' : 'btn small secondary'}
              onClick={() => setOpen(o => !o)} title={t('kbPanelTitle')} aria-label={t('kbPanelTitle')}
              style={variant === 'topbar' ? undefined : { display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <BookOpen size={16} aria-hidden="true" />{notes.length > 0 && <b>{notes.length}</b>}
      </button>
      {open && (
        <div role="dialog" aria-label={t('kbPanelTitle')} style={{
          position: 'fixed', top: 'var(--topbar-h, 56px)', right: 0, bottom: 0, width: 380,
          maxWidth: '95vw', background: 'var(--panel, #fff)', color: 'inherit', zIndex: 65,
          boxShadow: '-8px 0 30px rgba(0,0,0,0.25)', overflowY: 'auto', padding: 16,
          borderLeft: '1px solid var(--border, #dde3ec)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 6 }}><BookOpen size={20} aria-hidden="true" /> {t('kbPanelTitle')}</h3>
            <button className="btn small secondary" onClick={() => setOpen(false)} aria-label={t('close')}><X size={16} aria-hidden="true" /></button>
          </div>
          <p className="muted" style={{ fontSize: 13, margin: '4px 0 12px' }}>
            {scopes.map(s => `${s.scope_type}: ${s.scope_key}`).join(' · ')}
          </p>

          <AssistantBox />

          {notes.length === 0 && !adding && (
            <p className="muted">{t('kbNoNotes')}</p>
          )}
          {notes.map(note => (
            <div key={note.id} data-testid="kb-note" style={{
              border: '1px solid var(--border, #dde3ec)', borderRadius: 8,
              padding: '8px 10px', marginBottom: 8,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <b>{note.title}</b>
                {!wanted.has(scopeKeyOf(note)) ? null : canEdit
                  && (user?.role === 'admin' || note.created_by_id === user?.id) && (
                  <span style={{ whiteSpace: 'nowrap' }}>
                    <button className="btn small secondary" title={t('kbEdit')} onClick={() => {
                      setEditId(note.id); setAdding(true)
                      setForm({ title: note.title, body: note.body, url: note.url })
                    }}><PencilIcon size={14} /></button>{' '}
                    <button className="btn small secondary" title={t('kbDelete')} disabled={busy}
                            onClick={() => removeNote(note.id)}><Trash2Icon size={14} /></button>
                  </span>
                )}
              </div>
              {note.body && (
                <div style={{ whiteSpace: 'pre-wrap', fontSize: 14, marginTop: 4 }}>
                  {note.body}
                </div>
              )}
              {note.url && (
                <a href={note.url} target="_blank" rel="noreferrer"
                   style={{ display: 'inline-block', marginTop: 4, fontSize: 14 }}>
                  {isYouTube(note.url) ? <PlayIcon size={14} /> : <LinkIcon size={14} />}{' '}
                  {isYouTube(note.url) ? t('kbWatchVideo') : t('kbOpenLink')}
                </a>
              )}
              {note.created_by_name && (
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  {note.created_by_name}
                </div>
              )}
            </div>
          ))}

          {canEdit && !adding && (
            <button className="btn small" onClick={() => {
              setAdding(true); setEditId(null); setForm(EMPTY_FORM)
            }}>{t('kbAddNote')}</button>
          )}
          {adding && (
            <div style={{ marginTop: 8, display: 'grid', gap: 6 }}>
              <input aria-label={t('kbNoteTitle')} placeholder={t('kbNoteTitle')} value={form.title}
                     onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
              <textarea aria-label={t('kbNoteBody')} placeholder={t('kbNoteBody')} rows={4} value={form.body}
                        onChange={e => setForm(f => ({ ...f, body: e.target.value }))} />
              <input aria-label={t('kbNoteUrl')} placeholder={t('kbNoteUrl')} value={form.url}
                     onChange={e => setForm(f => ({ ...f, url: e.target.value }))} />
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn small" disabled={busy} onClick={saveNote}>{t('save')}</button>
                <button className="btn small secondary" onClick={() => {
                  setAdding(false); setEditId(null)
                }}>{t('cancel')}</button>
              </div>
            </div>
          )}

          <hr style={{ margin: '14px 0', border: 'none',
                       borderTop: '1px solid var(--border, #dde3ec)' }} />
          {sent && <p style={{ color: 'var(--ok, #067647)' }}>{t('kbTopicSent')}</p>}
          {!writesKnowledge(user?.role) ? null : !topicMode ? (
            <button className="btn small secondary" onClick={() => setTopicMode(true)}>
              <HandIcon size={14} /> {t('kbReportTopic')}
            </button>
          ) : (
            <div style={{ display: 'grid', gap: 6 }}>
              <input aria-label={t('kbTopicTitle')} placeholder={t('kbTopicTitle')} value={topicForm.title}
                     onChange={e => setTopicForm(f => ({ ...f, title: e.target.value }))} />
              <textarea aria-label={t('kbTopicBody')} placeholder={t('kbTopicBody')} rows={3} value={topicForm.body}
                        onChange={e => setTopicForm(f => ({ ...f, body: e.target.value }))} />
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn small" disabled={busy} onClick={sendTopic}>{t('kbSend')}</button>
                <button className="btn small secondary"
                        onClick={() => setTopicMode(false)}>{t('cancel')}</button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  )
}

// Baner nieprzeczytanych not eskalacyjnych (W16): widoczny na górze aplikacji,
// dopóki user nie potwierdzi „przeczytałem" każdej adresowanej do jego roli noty.
export function BulletinBanner() {
  const t = useT()
  const [items, setItems] = useState<KnowledgeBulletin[]>([])
  const [expanded, setExpanded] = useState(false)

  const reload = useCallback(() => {
    api.get<KnowledgeBulletin[]>('/api/knowledge/bulletins/unread')
      .then(setItems).catch(() => {})
  }, [])
  useEffect(() => { reload() }, [reload])
  // nowa nota eskalacyjna dociera bez przelogowania — w rytmie dzwonka (60 s, widoczna karta)
  useVisibleInterval(reload, 60_000)

  const { showToast } = useToast()
  // nota znika dopiero po zapisie potwierdzenia — błąd nie może udawać „przeczytane”
  const ack = (id: number) => api.post(`/api/knowledge/bulletins/${id}/ack`, {})
    .then(() => setItems(list => list.filter(b => b.id !== id)))
    .catch(err => showToast(errorMessage(err), 'error'))

  if (items.length === 0) return null
  return (
    <div role="alert" style={{
      background: '#7a2e0e', color: '#fff', padding: '8px 16px', fontSize: 14,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <b><MegaphoneIcon size={14} /> {t('kbUnreadBanner').replace('{n}', String(items.length))}</b>
        <button className="btn small secondary" onClick={() => setExpanded(e => !e)}>
          {expanded ? t('kbHide') : t('kbShow')}
        </button>
      </div>
      {expanded && items.map(b => (
        <div key={b.id} style={{ marginTop: 8, padding: '8px 10px',
                                 background: 'rgba(255,255,255,0.1)', borderRadius: 8 }}>
          <b>{b.title}</b>
          {b.body && <div style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>{b.body}</div>}
          <button className="btn small" style={{ marginTop: 6 }} onClick={() => ack(b.id)}>
            ✓ {t('kbMarkRead')}
          </button>
        </div>
      ))}
    </div>
  )
}
