// Okno potwierdzenia przeniesienia daty awizacji + pływający pasek akcji zbiorczych
// dla zaznaczonych kontenerów. Wyniesione z QueuePage.tsx.
import { useContext } from 'react'
import { formatDate } from '../../dates'
import { Modal } from '../../components'
import { LangContext, useT } from '../../i18n'
import type { Container } from '../../types'
import { formatDayHeader } from '../queueRows'
import { idLabel } from './cells'
import type { QueueMove } from './useQueueMove'

export function MoveConfirmModal({ mv, containers }: { mv: QueueMove; containers: Container[] }) {
  const t = useT()
  const { lang } = useContext(LangContext)
  const { pendingMove, moving, moveError } = mv
  if (!pendingMove) return null
  return (
    <Modal title={t('confirmMoveTitle')} onClose={() => mv.setPendingMove(null)} busy={moving}
           className="move-confirm">
        <p className="move-question">
          {t('confirmMoveQuestion')}{' '}
          <b>{formatDayHeader(pendingMove.day, lang).weekday}, {formatDayHeader(pendingMove.day, lang).full}</b>
          {' '}<span className="mono">({formatDate(pendingMove.day)})</span>
        </p>
        {pendingMove.ids.some(id => containers.find(x => x.id === id)?.planning_status === 'POTWIERDZONE') && (
          <p className="move-warning">{t('planEditConfirmed')}</p>
        )}
        <div style={{ overflowX: 'auto' }}>
          <table className="grid" style={{ minWidth: 720 }}>
            <thead>
              <tr>
                <th>{t('containerNo')}</th>
                <th>{t('currentDate')}</th>
                <th></th>
                <th>{t('targetDate')}</th>
              </tr>
            </thead>
            <tbody>
              {pendingMove.ids.map(id => {
                const c = containers.find(x => x.id === id)
                if (!c) return null
                return (
                  <tr key={id}>
                    <td className="mono strong">{idLabel(c)}</td>
                    <td className="mono date-cell">{formatDate(c.notify_date)}</td>
                    <td style={{ color: 'var(--muted)' }}>→</td>
                    <td className="mono strong date-cell">{formatDate(pendingMove.day)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {moveError && <p className="error">{moveError}</p>}
        <div className="actions">
          <button className="btn secondary" disabled={moving}
                  onClick={() => mv.setPendingMove(null)}>
            {t('cancel')}
          </button>
          <button className="btn" disabled={moving} onClick={mv.confirmMove}>
            {moving ? t('movingNow') : `${t('confirmMoveYes')} (${pendingMove.ids.length})`}
          </button>
        </div>
    </Modal>
  )
}
