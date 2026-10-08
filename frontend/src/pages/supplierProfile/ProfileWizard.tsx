// Kreator profilu dokumentów dostawcy — 4 kroki: dane → próbki → mapowanie CI/PL → test.
// „Dalej” zapisuje stan (PUT, bez zmiany statusu): podgląd próbek czyta zapisany znacznik PL
// i mapy. Koniec: „Zapisz jako szkic” albo „Aktywuj profil” (po teście; niezdane = confirm).
import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { Modal } from '../../components'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import { formOf, type Profile, type ProfileForm, type TestResult } from './profileModel'
import { MappingStep, SamplesStep } from './WizardSamples'
import TestStep from './WizardTest'
import { useConfirm } from '../../ConfirmDialog'

const STEPS = ['sdpStep1', 'sdpStep2', 'sdpStep3', 'sdpStep4'] as const

export default function ProfileWizard({ supplierId, supplierName, profile, onClose }: {
  supplierId: number
  supplierName: string
  profile: Profile
  onClose: () => void
}) {
  const t = useT()
  const { confirm } = useConfirm()
  const { showToast } = useToast()
  const [step, setStep] = useState(0)
  const [form, setForm] = useState<ProfileForm>(formOf(profile))
  const [samples, setSamples] = useState(profile.samples)
  const [results, setResults] = useState<TestResult[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const base = `/api/suppliers/${supplierId}/doc-profile`
  const patch = (p: Partial<ProfileForm>) => setForm(f => ({ ...f, ...p }))

  async function save(status: ProfileForm['status']): Promise<Profile | null> {
    setBusy(true)
    setError('')
    try {
      const saved = await api.put<Profile>(base, { ...form, status })
      setForm(formOf(saved))
      setSamples(saved.samples)
      return saved
    } catch (err) {
      setError(errorMessage(err))
      return null
    } finally {
      setBusy(false)
    }
  }

  async function go(next: number) {
    if (next > step && !(await save(form.status))) return
    setStep(next)
  }

  async function finish(status: ProfileForm['status']) {
    if (status === 'active' && !(results?.every(r => r.ok)) && !(await confirm(t('sdpActivateConfirm')))) return
    if (await save(status)) {
      showToast(t('sdpSaved'))
      onClose()
    }
  }

  return (
    <Modal title={t('sdpWizardTitle').replace('{name}', supplierName)} onClose={onClose}
           width={1040} className="sdp-wizard" busy={busy}>
      <ol className="sdp-steps" aria-label={t('sdpTitle')}>
        {STEPS.map((key, i) => (
          <li key={key} className={i === step ? 'on' : i < step ? 'done' : ''}>
            <button type="button" disabled={busy || i > step} onClick={() => setStep(i)}
                    aria-current={i === step ? 'step' : undefined}>
              <span className="sdp-step-no">{i + 1}</span>{t(key)}
            </button>
          </li>
        ))}
      </ol>

      <div className="sdp-body">
        {step === 0 && <DataStep form={form} patch={patch} />}
        {step === 1 && <SamplesStep base={base} samples={samples} setSamples={setSamples} />}
        {step === 2 && <MappingStep base={base} samples={samples} form={form} patch={patch} />}
        {step === 3 && <TestStep base={base} form={form} results={results}
                                 setResults={setResults} setSamples={setSamples} />}
      </div>

      {error && <p className="error">{error}</p>}
      <div className="sdp-actions">
        <button type="button" className="btn secondary" disabled={busy}
                onClick={() => (step === 0 ? onClose() : setStep(step - 1))}>
          {step === 0 ? t('cancel') : t('sdpBack')}
        </button>
        <span className="sdp-spacer" />
        {step < 3 ? (
          <button type="button" className="btn" disabled={busy} onClick={() => go(step + 1)}>
            {t('sdpNext')}
          </button>
        ) : (
          <>
            <button type="button" className="btn secondary" disabled={busy}
                    onClick={() => finish('draft')}>{t('sdpSaveDraft')}</button>
            <button type="button" className="btn" disabled={busy || !results}
                    onClick={() => finish('active')}>{t('sdpActivate')}</button>
          </>
        )}
      </div>
    </Modal>
  )
}

function DataStep({ form, patch }: { form: ProfileForm; patch: (p: Partial<ProfileForm>) => void }) {
  const t = useT()
  const [word, setWord] = useState('')
  const addWord = () => {
    const w = word.trim()
    if (w && !form.keywords.includes(w)) patch({ keywords: [...form.keywords, w] })
    setWord('')
  }
  return (
    <div className="form-grid">
      <label>{t('sdpCurrency')}
        <input value={form.currency} maxLength={3} placeholder="USD"
               onChange={e => patch({ currency: e.target.value.toUpperCase() })} />
      </label>
      <label>{t('sdpLanguage')}
        <input value={form.doc_language} maxLength={10} placeholder="en" list="sdp-langs"
               onChange={e => patch({ doc_language: e.target.value })} />
        <datalist id="sdp-langs">{['pl', 'en', 'de', 'zh', 'pt'].map(l => <option key={l} value={l} />)}</datalist>
      </label>
      <label>{t('sdpRefKind')}
        <select value={form.ref_kind}
                onChange={e => patch({ ref_kind: e.target.value as ProfileForm['ref_kind'] })}>
          {(['ours', 'supplier'] as const).map(k => <option key={k} value={k}>{t(`sdpRefKind_${k}`)}</option>)}
        </select>
      </label>
      <label>{t('sdpSplitMarker')}
        <input value={form.split_marker} maxLength={60} placeholder="PACKING LIST"
               onChange={e => patch({ split_marker: e.target.value })} />
        <span className="muted txt-xs">{t('sdpSplitMarkerHint')}</span>
      </label>
      <label>{t('sdpTolAmount')}
        <input type="number" min={0} max={100} step={0.1} value={form.tol_amount_pct}
               onChange={e => patch({ tol_amount_pct: Number(e.target.value) })} />
      </label>
      <label>{t('sdpTolQty')}
        <input type="number" min={0} max={100} step={0.1} value={form.tol_qty_pct}
               onChange={e => patch({ tol_qty_pct: Number(e.target.value) })} />
      </label>
      <label className="wide">{t('sdpKeywords')}
        <div className="sdp-chips">
          {form.keywords.map(k => (
            <span key={k} className="chip">{k}
              <button type="button" className="chip-x" aria-label={`${t('delete')} ${k}`}
                      onClick={() => patch({ keywords: form.keywords.filter(x => x !== k) })}>×</button>
            </span>
          ))}
          <input value={word} placeholder={t('sdpKeywordsHint')} aria-label={t('sdpKeywords')}
                 onChange={e => setWord(e.target.value)}
                 onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addWord() } }} />
        </div>
      </label>
    </div>
  )
}
