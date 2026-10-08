import { useT } from '../../i18n'

/** Stonowana etykieta powodu obserwacji (obcinana wielokropkiem, pełny tekst w podpowiedzi). */
export default function WatchReasonTag({ reason }: { reason: string }) {
  const t = useT()
  if (!reason) return null
  return (
    <span className="watch-reason-tag" title={`${t('watchReasonLabel')}: ${reason}`}>
      <span className="sr-only">{t('watchReasonLabel')}: </span>{reason}
    </span>
  )
}
