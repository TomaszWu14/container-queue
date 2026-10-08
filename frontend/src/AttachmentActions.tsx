// Pomyłka przy wgraniu (2026-10-06): „Podmień” = JEDNO żądanie z replaces_id (serwer zachowuje typ
// i usuwa stary plik w tej samej transakcji); po wysłaniu do agencji z powodem. „Usuń” po
// potwierdzeniu. Widoczność przycisków z flag API (can_delete / can_replace) — backend i tak pilnuje.
import { useConfirm } from './ConfirmDialog'
import { FileButton } from './FilePicker'
import { api, errorMessage } from './api'
import { useT } from './i18n'
import type { Attachment } from './types'

export function AttachmentActions({ attachment, containerId, busy, setBusy, onChanged, onError, linkClass }: {
  attachment: Attachment
  containerId: number
  busy: boolean
  setBusy: (busy: boolean) => void
  onChanged: () => void
  onError: (message: string) => void
  linkClass: string
}) {
  const t = useT()
  const { confirm, prompt } = useConfirm()
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); onError('')
    try { await fn(); onChanged() } catch (err) { onError(errorMessage(err)) } finally { setBusy(false) }
  }
  const shared = attachment.shared_with ?? []
  const remove = async () => {
    const also = shared.length ? ' ' + t('attAlsoIn').replace('{list}', shared.join(', ')) : ''
    if (!(await confirm(t('attDeleteConfirm').replace('{name}', attachment.filename) + also, { danger: true }))) return
    run(() => api.del(`/api/attachments/${attachment.id}`))
  }
  const unlink = async () => {
    const text = t('attUnlinkConfirm').replace('{name}', attachment.filename)
      .replace('{owner}', attachment.owner_container_no ?? '')
    if (!(await confirm(text))) return
    run(() => api.del(`/api/containers/${containerId}/attachments/${attachment.id}/link`))
  }
  const replace = async (file: File) => {
    let reason = ''
    if (attachment.replace_needs_reason) {
      reason = ((await prompt(t('attReplaceReason'))) ?? '').trim()
      if (!reason) return
    }
    run(() => api.upload(`/api/containers/${containerId}/attachments`, file, 'file',
      { replaces_id: String(attachment.id), ...(reason ? { replace_reason: reason } : {}) }))
  }
  const canReplace = attachment.can_replace ?? true
  const canDelete = attachment.can_delete ?? true
  return (
    <>
      {canReplace && <FileButton className={linkClass} title={t('attReplaceHint')} disabled={busy}
                                 onFiles={([f]) => { if (f) replace(f) }}>{t('attReplace')}</FileButton>}
      {canDelete && <button type="button" className={linkClass} disabled={busy} onClick={remove}>{t('attDelete')}</button>}
      {attachment.can_unlink && <button type="button" className={linkClass} disabled={busy}
                                        onClick={unlink}>{t('attUnlink')}</button>}
    </>
  )
}

/** „wspólny z X, Y” — plik powiązany z kilkoma kontenerami (podmiana u właściciela działa wszędzie). */
export function SharedBadge({ attachment }: { attachment: Attachment }) {
  const t = useT()
  const shared = attachment.shared_with ?? []
  if (!shared.length) return null
  return <span className="badge" title={t('attSharedHint')} style={{ marginLeft: 6 }}>
    {t('attSharedWith').replace('{list}', shared.join(', '))}</span>
}
