import { defineFeature } from '../feature'

// Master data → Armatorzy: dni wolne od demurrage (kontener może nadpisać ręcznie), 2026-09-28
export default defineFeature({
  pl: { carrierFreeDays: 'Dni wolne od demurrage' },
  en: { carrierFreeDays: 'Demurrage free days' },
  pt: { carrierFreeDays: 'Dias livres de demurrage' },
})
