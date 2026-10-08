// Podgląd na żywo: wycinek kolejki (pasek górny, pasek dnia, wiersze DLT / ACME / bez magazynu)
// w barwach edytowanego motywu — zmienne ustawione na kontenerze, niezależnie od motywu admina.
import type { CSSProperties } from 'react'
import { useT } from '../../../i18n'

const ROWS: [string, string, string, string][] = [
  ['dlt', 'FFAU6240568', 'NORTHBRIDGE', 'DLT'],
  ['acme', 'TGBU8339125', 'PULIN', 'ACME'],
  ['dlt', 'ECMU8850883', 'NORTHBRIDGE', 'DLT'],
  ['none', 'OOCU9648783', 'FLYWORLD', '—'],
  ['acme', 'CSNU9264513', 'FORMED + EASYWAY', 'ACME'],
]

export function ColorsPreview({ colors }: { colors: Record<string, string> }) {
  const t = useT()
  return (
    <div className="colprev" style={colors as CSSProperties} aria-label={t('colPreview')} role="img">
      <div className="colprev-chrome"><b>{t('colPrevQueue')}</b><span>{t('colPrevOther')}</span></div>
      <div className="colprev-tabs"><b>{t('colPrevAll')}</b><span>{t('colPrevLate')}</span></div>
      <table>
        <tbody>
          <tr className="colprev-day"><td colSpan={4}>{t('colPrevDay')}</td></tr>
          {ROWS.map(([wh, no, sup, name]) => (
            <tr key={no} className={`colprev-row wh-${wh}`}>
              <td className="mono">{no}</td><td>{sup}</td><td className="colprev-wh">{name}</td>
              <td className="colprev-muted">18.09.2026</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
