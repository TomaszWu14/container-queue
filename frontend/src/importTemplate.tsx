import { DownloadIcon } from 'lucide-react'
// „Pobierz wzór" przy importach — xlsx z backendu (/api/import/templates/{kind}) z nagłówkami
// w brzmieniu parsera, przykładowym wierszem i arkuszem „Instrukcja".
import { downloadFile, errorMessage } from './api'
import { useToast } from './feedback'
import { useT } from './i18n'

export type TemplateKind = 'materials' | 'marm' | 'lfa1' | 'ekko' | 'ref' | 'etd' | 'queue'
  | 'dlt' | 'ports' | 'po' | 'paz' | 'issues'

const LABEL: Record<TemplateKind, string> = {
  materials: 'tplMaterials', marm: 'tplMarm', lfa1: 'tplLfa1', ekko: 'tplEkko', ref: 'tplRef',
  etd: 'tplEtd', queue: 'tplQueue', dlt: 'tplDlt', ports: 'tplPorts', po: 'tplPo', paz: 'tplPaz',
  issues: 'tplIssues',
}

// jeden wzór: „⬇ Pobierz wzór"; kilka: „⬇ Wzory: MARM · EKKO · …"
export function TemplateButtons({ kinds }: { kinds: TemplateKind[] }) {
  const t = useT()
  const { showToast } = useToast()
  const get = (kind: TemplateKind) =>
    downloadFile(`/api/import/templates/${kind}`, `wzor_${kind}.xlsx`)
      .catch(err => showToast(errorMessage(err), 'error'))
  return (
    <span className="row" style={{ gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      {kinds.length > 1 && <span className="muted" style={{ fontSize: 14 }}><DownloadIcon size={14} /> {t('importTemplates')}:</span>}
      {kinds.map(kind => (
        <button key={kind} type="button" className="btn small secondary" title={t('importTemplateHint')}
                onClick={() => get(kind)}>
          {kinds.length > 1 ? t(LABEL[kind]) : <><DownloadIcon size={14} /> {t('importTemplate')}</>}
        </button>
      ))}
    </span>
  )
}
