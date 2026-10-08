// Kafelki dokumentów dostawy (DocumentTiles.tsx, spec 2026-10-01-kafelki-dokumentow)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    dtTitle: 'Dokumenty', dtTileCol: 'Kafelek', dtLoaded: 'załadowanych', dtMissing: 'brakuje',
    dtName_PI: 'Proforma Invoice', dtName_CI: 'Faktura handlowa', dtName_PL: 'Packing List',
    dtName_BL: 'Konosament (B/L)', dtName_SAD_DRAFT: 'Draft SAD', dtName_SAD_PZ: 'SAD po odprawie',
    dtName_SAD_PW: 'Zwolnienie (SAD-PW)',
    dtState_none: 'brak', dtState_present: 'jest', dtState_ok: 'sprawdzony',
    dtState_warn: 'niepewny / czeka', dtState_bad: 'sprzeczny / do poprawy',
    dtNoFile: 'Brak pliku', dtOpen: 'Otwórz najnowszy plik',
    dtManage: 'zarządzaj',
  },
  en: {
    dtTitle: 'Documents', dtTileCol: 'Tile', dtLoaded: 'loaded', dtMissing: 'missing',
    dtName_PI: 'Proforma Invoice', dtName_CI: 'Commercial invoice', dtName_PL: 'Packing List',
    dtName_BL: 'Bill of lading (B/L)', dtName_SAD_DRAFT: 'SAD draft', dtName_SAD_PZ: 'SAD after clearance',
    dtName_SAD_PW: 'Release (SAD-PW)',
    dtState_none: 'missing', dtState_present: 'uploaded', dtState_ok: 'checked',
    dtState_warn: 'uncertain / pending', dtState_bad: 'conflict / needs changes',
    dtNoFile: 'No file', dtOpen: 'Open the latest file',
    dtManage: 'manage',
  },
  pt: {
    dtTitle: 'Documentos', dtTileCol: 'Mosaico', dtLoaded: 'carregados', dtMissing: 'em falta',
    dtName_PI: 'Fatura proforma', dtName_CI: 'Fatura comercial', dtName_PL: 'Packing List',
    dtName_BL: 'Conhecimento de embarque (B/L)', dtName_SAD_DRAFT: 'Rascunho SAD', dtName_SAD_PZ: 'SAD após desalfandegamento',
    dtName_SAD_PW: 'Libertação (SAD-PW)',
    dtState_none: 'em falta', dtState_present: 'carregado', dtState_ok: 'verificado',
    dtState_warn: 'incerto / pendente', dtState_bad: 'em conflito / a corrigir',
    dtNoFile: 'Sem ficheiro', dtOpen: 'Abrir o ficheiro mais recente',
    dtManage: 'gerir',
  },
})
