import { defineFeature } from '../feature'

// Pełny eksport EKKO/MARM — brakujące rekordy oznaczane „brak w SAP” (DATA-003, 2026-09-28)
export default defineFeature({
  pl: { sapMissingBadge: 'brak w SAP', sapFullExport: 'To pełny eksport SAP — oznacz {n} brakujących jako „brak w SAP” (bez kasowania)' },
  en: { sapMissingBadge: 'not in SAP', sapFullExport: 'This is a full SAP export — mark {n} missing as “not in SAP” (never deleted)' },
  pt: { sapMissingBadge: 'não existe no SAP', sapFullExport: 'É uma exportação SAP completa — marcar {n} em falta como “não existe no SAP” (sem eliminar)' },
})
