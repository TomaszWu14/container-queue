import { defineFeature } from '../feature'

// Synchronizacja kolejki z SharePoint tylko ręcznie — okres dwutorowy Excel ↔ aplikacja (2026-09-28)
export default defineFeature({
  pl: { spSyncNow: 'Synchronizuj teraz z SharePoint', spSyncDone: 'Zsynchronizowano z arkuszem SharePoint.', spSyncUnchanged: 'Arkusz bez zmian od ostatniej synchronizacji.' },
  en: { spSyncNow: 'Sync now with SharePoint', spSyncDone: 'Synchronised with the SharePoint sheet.', spSyncUnchanged: 'Sheet unchanged since last sync.' },
  pt: { spSyncNow: 'Sincronizar agora com SharePoint', spSyncDone: 'Sincronizado com a folha SharePoint.', spSyncUnchanged: 'Folha sem alterações desde a última sincronização.' },
})
