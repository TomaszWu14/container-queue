import { FileTextIcon, FlagIcon } from 'lucide-react'
// Akcje w nagłówku pełnej karty (wydzielone z ContainerPage 2026-09-30 bez zmian zachowania):
// wiedza kontekstowa, menu „Więcej” (flaga śledzenia, CMR, karta rozładunku, link),
// rozładunek (magazyn), zmiana statusu, edycja.
import { useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUser } from '../../App'
import { api, errorMessage } from '../../api'
import { Modal } from '../../components'
import { useConfirm } from '../../ConfirmDialog'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import KnowledgePanel from '../../KnowledgePanel'
import { MoreMenu } from '../../MoreMenu'
import type { Container } from '../../types'

// powody flagi śledzenia — wartości muszą zgadzać się z SPECIAL_REASONS w backendzie
const SPECIAL_REASONS = ['zlecenie_klienta', 'pilne', 'kontrola_jakosci',
  'nowe_produkty', 'nowy_producent'] as const

export default function ContainerActions({ container, setContainer, onStatus, onEdit }: {
  container: Container
  setContainer: Dispatch<SetStateAction<Container | null>>
  onStatus: () => void
  onEdit: () => void
}) {
  const t = useT()
  const { confirm, prompt } = useConfirm()
  const user = useUser()
  const navigate = useNavigate()
  const { showToast } = useToast()
  // formularz flagi śledzenia (powód + notatka); null = zamknięty
  const [flagForm, setFlagForm] = useState<{ reason: string; note: string } | null>(null)
  const [markingUnloaded, setMarkingUnloaded] = useState(false)

  const canEdit = user?.role === 'admin' || user?.role === 'logistics'
  const isWarehouse = user?.role === 'warehouse'
  const isForwarder = user?.role === 'forwarder'
  const isSales = user?.role === 'sales'

  const markUnloaded = async () => {
    // decyzja 2026-09-28: kontener bez awizacji można przyjąć, ale z notatką „dlaczego”
    let note = ''
    if (['AWIZOWANY', 'W_DOSTAWIE'].includes(container.status)) {
      if (!(await confirm(t('markUnloadedConfirm')))) return
    } else {
      const answer = await prompt(t('markUnloadedNoAvizo'))
      if (answer === null) return
      if (!answer.trim()) { showToast(t('markUnloadedNoteRequired')); return }
      note = answer.trim()
    }
    setMarkingUnloaded(true)
    try {
      const saved = await api.post<Container>(`/api/containers/${container.id}/status`,
        { status: 'DOSTARCZONY', note })
      setContainer(saved)
      showToast(saved?.docs_warning || t('toastStatusChanged'), saved?.docs_warning ? 'error' : undefined)
    } catch (err) {
      showToast(errorMessage(err))
    } finally {
      setMarkingUnloaded(false)
    }
  }

  return (
    <div className="row ct-head-actions">
      {flagForm && (
        <Modal title={t('specialFlag')} onClose={() => setFlagForm(null)}>
            <label className="cform-label">{t('specialReason')}
              <select value={flagForm.reason}
                      onChange={e => setFlagForm(f => f && { ...f, reason: e.target.value })}>
                <option value="">—</option>
                {SPECIAL_REASONS.map(r => <option key={r} value={r}>{t(`reason_${r}`)}</option>)}
              </select>
            </label>
            <label className="cform-label">{t('specialNote')}
              <textarea rows={2} value={flagForm.note}
                        onChange={e => setFlagForm(f => f && { ...f, note: e.target.value })} />
            </label>
            <div className="row" style={{ justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
              <button className="btn secondary" onClick={() => setFlagForm(null)}>{t('cancel')}</button>
              <button className="btn" onClick={async () => {
                try {
                  const res = await api.post<{ is_special: boolean; special_reason: string | null; special_note: string }>(
                    `/api/containers/${container.id}/special`,
                    { is_special: true, reason: flagForm.reason || null, note: flagForm.note })
                  setContainer(c => c && { ...c, is_special: res.is_special,
                    special_reason: res.special_reason, special_note: res.special_note })
                  setFlagForm(null)
                  showToast(t('specialOn'), 'success')
                } catch (err) { showToast(errorMessage(err), 'error') }
              }}>{t('save')}</button>
            </div>
        </Modal>
      )}
      {/* wiedza kontekstowa: dostawca + port + typy brakujących dokumentów kontenera */}
      <KnowledgePanel scopes={[
        ...(container.supplier_name
          ? [{ scope_type: 'supplier' as const, scope_key: container.supplier_name }] : []),
        ...(container.port_name
          ? [{ scope_type: 'port' as const, scope_key: container.port_name }] : []),
        ...(container.missing_documents ?? []).map(name =>
          ({ scope_type: 'document_type' as const, scope_key: name })),
      ]} />
      {/* A27/A28: na wierzchu tylko główne akcje (Zmień status, Edytuj); reszta w „Więcej” —
          7 równorzędnych przycisków zajmowało na telefonie trzy rzędy */}
      {(canEdit || !isSales) && <MoreMenu label={t('ctMore')}>
      {canEdit && (
        <button type="button" role="menuitem" className={container.is_special ? 'active' : undefined}
                title={t('specialToggle')}
                onClick={async () => {
                  if (!container.is_special) {   // włączenie → formularz powodu
                    setFlagForm({ reason: '', note: '' }); return
                  }
                  try {                            // wyłączenie → od razu
                    const res = await api.post<{ is_special: boolean }>(
                      `/api/containers/${container.id}/special`, { is_special: false })
                    setContainer(c => c && { ...c, is_special: res.is_special,
                      special_reason: null, special_note: '' })
                    showToast(t('specialOff'), 'success')
                  } catch (err) { showToast(errorMessage(err), 'error') }
                }}>
          <FlagIcon size={14} /> {t('specialFlag')}{container.is_special ? ' ✓' : ''}
        </button>
      )}
      {(canEdit || isWarehouse || isForwarder) && (
        <button type="button" role="menuitem"
                onClick={() => window.open(`/api/containers/${container.id}/cmr`, '_blank')}>
          <FileTextIcon size={14} /> {t('cmrPrint')}
        </button>
      )}
      {!isSales && (
        <button type="button" role="menuitem" onClick={() => navigate(`/kontenery/${container.id}/karta`)}>
          {t('unloadCard')}
        </button>
      )}
      </MoreMenu>}
      {isWarehouse && (
        <button className="btn secondary" onClick={markUnloaded} disabled={markingUnloaded}>
          {markingUnloaded ? '…' : t('markUnloaded')}
        </button>
      )}
      {(canEdit || isWarehouse) && (
        <button className="btn secondary" onClick={onStatus}>
          {isWarehouse ? t('confirmUnload') : t('changeStatus')}
        </button>
      )}
      {canEdit && <button className="btn" onClick={onEdit}>{t('edit')}</button>}
    </div>
  )
}
