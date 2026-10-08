import { defineFeature } from '../feature'

// BIZ-008: korekty obiegu zlecenia transportowego przez logistykę (zawsze z powodem)
export default defineFeature({
  pl: {
    orderReissue: 'Wystaw ponownie', orderRevertDone: 'Cofnij do realizacji',
    orderCorrectionPrompt: 'Powód korekty (zobaczy go spedytor):',
    orderCorrectionReasonRequired: 'Korekta wymaga podania powodu.',
  },
  en: {
    orderReissue: 'Reissue', orderRevertDone: 'Back to in progress',
    orderCorrectionPrompt: 'Reason for the correction (the forwarder will see it):',
    orderCorrectionReasonRequired: 'A correction requires a reason.',
  },
  pt: {
    orderReissue: 'Reemitir', orderRevertDone: 'Voltar a em execução',
    orderCorrectionPrompt: 'Motivo da correção (o transitário verá):',
    orderCorrectionReasonRequired: 'A correção exige um motivo.',
  },
})
