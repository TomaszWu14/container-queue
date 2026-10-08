import { ShuffleIcon } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
// Zakładki spółek jako pigułki ≤32px z licznikiem-badge (Acme/DLT/Borealis/Cobalt/PT) + Tranzyt.
// Aktywna pigułka ma zawsze kolor akcentu (jeden akcent); spółkę pokazuje kropka --co-* (w dark jaśniejsza).
// „Analiza rozładunków" przeszła do menu Analiza w topbarze (moduł ?spolka=analysis zostaje).
import { HelpTip } from '../../HelpTip'
import { useT } from '../../i18n'
import type { Module } from './config'

// zakładki spółek: moduł → [klucz etykiety | stała etykieta, klucz licznika]
const COMPANY_TABS: [Module, string | null, string][] = [
  ['acme', 'moduleAcme', 'ACME'],
  ['dlt', null, 'DLT'],
  ['borealis', 'moduleBorealis', 'BOREALIS'],
  ['cobalt', 'moduleYellow', 'COBALT'],
  ['pt', 'modulePt', 'PT'],
]

export default function CompanyTabs({ module, setModule, counts, transitCount }: {
  module: Module
  setModule: (m: Module) => void
  counts: Record<string, number> | null  // null = nie wczytano
  transitCount: number | null
}) {
  const t = useT()
  const pill = (m: Module, label: ReactNode, n: number | null, extra = '', title?: string) => (
    <button key={m} type="button" title={title} aria-pressed={module === m}
            className={`kq-pill${module === m ? ' active' : ''}${n === 0 ? ' zero' : ''}${extra}`}
            onClick={() => setModule(m)}>
      {label}{n !== null && <span className="kq-pill-n mono">{n}</span>}
    </button>
  )
  return (
    <div className="kq-pills" role="group" aria-label={t('kqCompanies')}>
      {COMPANY_TABS.map(([m, labelKey, countKey]) =>
        pill(m, <>
          <span className="kq-pill-dot" aria-hidden="true"
                style={{ '--kq-co': `var(--co-${m})` } as CSSProperties} />
          {labelKey ? t(labelKey) : countKey}
        </>, counts ? counts[countKey] ?? 0 : null))}
      <span className="kq-vsep" aria-hidden="true" />
      {pill('tranzyt', <><ShuffleIcon size={14} /> {t('moduleTransit')}</>, transitCount, ' transit', t('moduleTransitHint'))}
      <HelpTip label={`${t('helpLabel')}: ${t('moduleTransit')}`} text={t('helpTransit')} />
    </div>
  )
}
