// Źródło importu w SAP (2026-09-29, wariant A): szara plakietka z nazwą tabeli SE16N + ⓘ
// z opisem — co import daje, skąd wziąć plik, kolumna-klucz.
import { HelpTip } from './HelpTip'
import { useT } from './i18n'

export type SapTable = 'EKKO' | 'EKPO' | 'MARM' | 'LFA1'

export function SapSource({ table }: { table: SapTable }) {
  const t = useT()
  return (
    <span className="sap-src">
      <span className="sap-tag">{table}</span>
      <HelpTip icon="i" label={`${t('se16nSource')}: ${table}`} text={t(`se16n_${table}`)} />
    </span>
  )
}
