import { useT } from '../i18n'

export interface ImportRowError {
  row: number
  reason: string
  order_number?: string
  position?: string
  material_no?: string
  unit?: string
}

// błędne wiersze importu SAP (REF, MARM): pominięte, z powodem — do poprawy w pliku
export function ImportErrors({ errors }: { errors?: ImportRowError[] }) {
  const t = useT()
  if (!errors?.length) return null
  return (
    <div className="import-rows">
      <p className="error">{t('importRowErrors').replace('{n}', String(errors.length))}</p>
      <ul>
        {errors.map(e => (
          <li key={e.row}>
            {t('importErrRow')} {e.row}:{' '}
            <span className="mono">
              {[e.order_number ?? e.material_no, e.position ?? e.unit].filter(Boolean).join(' / ') || '—'}
            </span>{' '}— {e.reason}
          </li>
        ))}
      </ul>
    </div>
  )
}
