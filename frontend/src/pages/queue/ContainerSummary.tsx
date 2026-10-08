import { StarIcon } from 'lucide-react'
// Nagłówek kontenera „czego to dotyczy” — wspólny dla szuflady kolejki i pełnej karty:
// numer + statusy + gwiazdka z powodem, dostawca · statek · PO, pasek etapów.
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useT } from '../../i18n'
import type { Container } from '../../types'
import { CONTAINER_STATUSES } from '../../types'
import WatchReasonTag from '../watch/WatchReasonTag'
import { idLabel, MultiCell } from './cells'
import { stageName } from './enterprise'

export default function ContainerSummary({ c, watchReason, heading = false, badges, meta }: {
  c: Container
  watchReason?: string   // undefined = nie obserwujesz; '' = ★ bez powodu
  heading?: boolean      // pełna karta: numer jako <h1>
  badges?: ReactNode     // dodatkowe plakietki przy numerze (flaga, utknął)
  meta?: ReactNode       // linia pod dostawcą (pełna karta: spółka · magazyn · dostawa)
}) {
  const t = useT()
  const stage = CONTAINER_STATUSES.indexOf(c.status)
  const po = c.order_numbers || c.order_number
  const [poOpen, setPoOpen] = useState(false)   // wszystkie PO kontenera, nie tylko pierwszy
  const no = heading ? <h1 className="kq-dr-no mono">{idLabel(c)}</h1> : <b className="kq-dr-no mono">{idLabel(c)}</b>
  return (
    <>
      <div className="kq-dr-row">
        {no}
        <span className={`badge st-${c.status}`} title={t(`st_${c.status}`)}>{stageName(t(`st_${c.status}`))}</span>
        {c.is_delayed && <span className="badge delayed">{t('delayed')}</span>}
        {badges}
        {watchReason !== undefined && (
          <span className="watch-mark">
            <StarIcon size={14} fill="currentColor" role="img"
                      aria-label={watchReason ? t('watchReasonLabel') : t('watchingNoReason')} />
            <WatchReasonTag reason={watchReason} />
          </span>
        )}
      </div>
      <div className="kq-dr-sub">
        {[c.supplier_name, c.vessel].filter(Boolean).join(' · ')}
        {po && <> · PO <MultiCell raw={po} open={poOpen} onToggle={() => setPoOpen(o => !o)} copyable /></>}
      </div>
      {meta}
      <div className="kq-dr-stages">
        {CONTAINER_STATUSES.map((s, i) => (
          <i key={s} title={t(`st_${s}`)} className={i < stage ? 'done' : i === stage ? 'cur' : ''} />
        ))}
      </div>
      <div className="kq-dr-stage">
        {t('kqdStageOf').replace('{n}', String(stage + 1)).replace('{m}', String(CONTAINER_STATUSES.length))}
        {' · '}{stageName(t(`st_${c.status}`))}
      </div>
    </>
  )
}
