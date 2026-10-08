// Kroki 2–3 kreatora: próbki PDF (upload/usunięcie + podgląd tabeli) i mapowanie ról kolumn
// CI/PL na tabeli z próbki (dropdown ról na nagłówku; auto-propozycja jak w compare).
import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import {
  COLUMN_ROLES, REQUIRED_ROLES, hasRequired, proposeRoles, roleOf, assignRole,
  type DocKind, type Preview, type ProfileForm, type Sample,
} from './profileModel'
import { useConfirm } from '../../ConfirmDialog'

function usePreview(base: string, sampleId: number | null, kind: DocKind) {
  const [preview, setPreview] = useState<Preview | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (sampleId === null) return
    let live = true
    setPreview(null)
    setError('')
    api.get<Preview>(`${base}/samples/${sampleId}/preview?kind=${kind}`)
      .then(p => { if (live) setPreview(p) })
      .catch(err => { if (live) setError(errorMessage(err)) })
    return () => { live = false }
  }, [base, sampleId, kind])
  return { preview, error }
}

const pagesText = (pages: number[]) => pages.length ? pages.join(', ') : '—'

function PreviewTable({ preview, roleFor, onRole }: {
  preview: Preview
  roleFor?: (header: string) => string
  onRole?: (header: string, role: string) => void
}) {
  const t = useT()
  if (!preview.found) return <p className="muted">{t('sdpNoTable')}</p>
  return (
    <div className="table-scroll sdp-preview">
      <table className="grid">
        <thead>
          <tr>
            {preview.headers.map((h, i) => {
              const role = roleFor?.(h) ?? ''
              return (
                <th key={i} className={role ? 'mapped' : ''}>
                  <div className="sdp-head">{h || '—'}</div>
                  {onRole && (
                    <select value={role} aria-label={h || `#${i + 1}`} disabled={!h}
                            onChange={e => onRole(h, e.target.value)}>
                      <option value="">{t('sdpSkip')}</option>
                      {COLUMN_ROLES.map(r => (
                        <option key={r} value={r}>
                          {t(`sdpRole_${r}`)}{(REQUIRED_ROLES as readonly string[]).includes(r) ? ' *' : ''}
                        </option>
                      ))}
                    </select>
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((row, r) => (
            <tr key={r}>{row.map((c, i) => <td key={i} className="mono">{c}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SamplePicker({ samples, value, onChange }: {
  samples: Sample[]; value: number | null; onChange: (id: number) => void
}) {
  const t = useT()
  return (
    <label className="sdp-inline">{t('sdpPickSample')}
      <select value={value ?? ''} onChange={e => onChange(Number(e.target.value))}>
        {samples.map(s => <option key={s.id} value={s.id}>{s.filename}</option>)}
      </select>
    </label>
  )
}

export function SamplesStep({ base, samples, setSamples }: {
  base: string; samples: Sample[]; setSamples: (s: Sample[]) => void
}) {
  const t = useT()
  const { confirm } = useConfirm()
  const [picked, setPicked] = useState<number | null>(samples[0]?.id ?? null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const current = samples.some(s => s.id === picked) ? picked : samples[0]?.id ?? null
  const { preview, error: previewError } = usePreview(base, current, 'ci')

  async function upload(files: FileList | null) {
    if (!files?.length) return
    setBusy(true)
    setError('')
    let list = samples
    try {
      for (const file of Array.from(files)) {
        list = [...list, await api.upload<Sample>(`${base}/samples`, file)]
        setSamples(list)
        setPicked(list[list.length - 1].id)
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function remove(s: Sample) {
    if (!(await confirm(t('sdpRemoveConfirm').replace('{name}', s.filename), { danger: true }))) return
    try {
      await api.del(`${base}/samples/${s.id}`)
      setSamples(samples.filter(x => x.id !== s.id))
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div className="sdp-samples">
      <div className="sdp-drop">
        <label className="btn small">
          {t('sdpUpload')}
          <input type="file" accept="application/pdf,.pdf" multiple hidden disabled={busy}
                 data-testid="sdp-upload" onChange={e => { upload(e.target.files); e.target.value = '' }} />
        </label>
        <span className="muted txt-sm">{t('sdpSamplesMax')} · {samples.length}/10</span>
      </div>
      {error && <p className="error">{error}</p>}
      <ul className="sdp-sample-list">
        {samples.map(s => (
          <li key={s.id} className={s.id === current ? 'on' : ''}>
            <button type="button" className="sdp-link" onClick={() => setPicked(s.id)}>{s.filename}</button>
            {s.id === current && preview && (
              <span className="muted txt-xs">
                {t('sdpPagesSplit').replace('{ci}', pagesText(preview.pages.ci))
                  .replace('{pl}', pagesText(preview.pages.pl))}
              </span>
            )}
            <button type="button" className="btn small ghost" aria-label={`${t('sdpRemoveSample')} ${s.filename}`}
                    onClick={() => remove(s)}>×</button>
          </li>
        ))}
      </ul>
      {previewError && <p className="error">{previewError}</p>}
      {preview && <PreviewTable preview={preview} />}
    </div>
  )
}

export function MappingStep({ base, samples, form, patch }: {
  base: string; samples: Sample[]; form: ProfileForm; patch: (p: Partial<ProfileForm>) => void
}) {
  const t = useT()
  const [kind, setKind] = useState<DocKind>('ci')
  const [picked, setPicked] = useState<number | null>(samples[0]?.id ?? null)
  const { preview, error } = usePreview(base, picked, kind)
  const key = kind === 'ci' ? 'ci_map' : 'pl_map'
  const map = form[key]

  // auto-propozycja ról z detekcji ekstraktora — tylko role jeszcze niezmapowane
  useEffect(() => {
    if (!preview?.found) return
    const proposed = proposeRoles(map, preview.headers, preview.detected)
    if (proposed !== map) patch({ [key]: proposed })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview])

  if (!samples.length) return <p className="muted">{t('sdpNoSamples')}</p>
  return (
    <div className="sdp-mapping">
      <div className="sdp-mapping-bar">
        <div className="tabs" role="tablist">
          {(['ci', 'pl'] as const).map(k => (
            <button key={k} type="button" role="tab" aria-selected={kind === k}
                    className={kind === k ? 'active' : ''} onClick={() => setKind(k)}>
              {k.toUpperCase()} <span className={hasRequired(form[k === 'ci' ? 'ci_map' : 'pl_map']) ? 'sdp-ok' : 'sdp-warn'}>
                {hasRequired(form[k === 'ci' ? 'ci_map' : 'pl_map']) ? '✓' : '!'}</span>
            </button>
          ))}
        </div>
        <SamplePicker samples={samples} value={picked} onChange={setPicked} />
      </div>
      <p className="muted txt-sm">{t('sdpRequired')} · {t('sdpAutoProposed')}</p>
      {error && <p className="error">{error}</p>}
      {preview && (
        <PreviewTable preview={preview} roleFor={h => roleOf(map, h)}
                      onRole={(h, role) => patch({ [key]: assignRole(map, h, role) })} />
      )}
    </div>
  )
}
