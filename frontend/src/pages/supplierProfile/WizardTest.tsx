import { CheckIcon, TriangleAlertIcon } from 'lucide-react'
// Krok 4 kreatora: test NIEZAPISANEGO stanu profilu na wszystkich próbkach
// (backend: bez tworzenia faktur; wynik per plik trafia też do próbki jako last_test).
import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { useT } from '../../i18n'
import type { ProfileForm, Sample, TestResult } from './profileModel'

const pagesText = (pages: number[]) => pages.length ? pages.join(', ') : '—'

export default function TestStep({ base, form, results, setResults, setSamples }: {
  base: string
  form: ProfileForm
  results: TestResult[] | null
  setResults: (r: TestResult[]) => void
  setSamples: (fn: (s: Sample[]) => Sample[]) => void
}) {
  const t = useT()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function run() {
    setBusy(true)
    setError('')
    try {
      const res = await api.post<{ ok: boolean; results: TestResult[] }>(`${base}/test`, form)
      setResults(res.results)
      setSamples(list => list.map(s => {
        const r = res.results.find(x => x.sample_id === s.id)
        return r ? { ...s, last_test: r } : s
      }))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const allOk = !!results?.length && results.every(r => r.ok)
  return (
    <div className="sdp-test">
      <div className="sdp-run">
        <button type="button" className="btn secondary" disabled={busy} onClick={run}>
          {t('sdpRunTest')}
        </button>
        <span className="muted txt-sm">
          {t('sdpTolerances')}: {t('sdpTolAmount')}: {form.tol_amount_pct} · {t('sdpTolQty')}: {form.tol_qty_pct}
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      {results && (
        <>
          <p className={allOk ? 'sdp-verdict ok' : 'sdp-verdict warn'} role="status">
            {allOk ? t('sdpAllOk') : t('sdpSomeFail')}
          </p>
          <div className="table-scroll">
            <table className="grid">
              <thead>
                <tr>
                  <th>{t('sdpTestFile')}</th>
                  <th>CI / PL</th>
                  <th className="num">{t('sdpTestItems')}</th>
                  <th className="num">{t('sdpTestMatched')}</th>
                  <th className="num">{t('sdpTestSum')}</th>
                  <th>{t('sdpTestResult')}</th>
                </tr>
              </thead>
              <tbody>
                {results.map(r => (
                  <tr key={r.sample_id}>
                    <td>{r.filename}</td>
                    <td className="mono nowrap">{pagesText(r.pages.ci)} / {pagesText(r.pages.pl)}</td>
                    <td className="num mono">{r.ci_items} / {r.pl_items}</td>
                    <td className="num mono">{r.matched}/{r.ci_items}</td>
                    <td className="num mono nowrap">
                      {r.total == null ? (r.sum_items ?? '—') : `${r.sum_items} / ${r.total}`}
                    </td>
                    <td>
                      <span className={r.ok ? 'sdp-ok' : 'sdp-warn'}>{r.ok ? <CheckIcon size={14} /> : <TriangleAlertIcon size={14} />}</span>{' '}
                      {r.errors.map(e => t(`sdpErr_${e}`)).join('; ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
