import { defineFeature } from '../feature'

// Panel admina → System → SMS do kierowców (2026-09-28)
export default defineFeature({
  pl: {
    smsSettingsTab: 'SMS do kierowców', smsSaved: 'Zapisano ustawienia SMS.',
    smsSettingsHint: 'Przypomnienia o dostawie wysyłane automatycznie kierowcom (czas polski).',
    smsReminderEnabled: 'Wysyłaj przypomnienia', smsReminderHour: 'Godzina wysyłki (0–23)',
    smsReminderDays: 'Ile dni przed dostawą (np. „2, 1” = dwa przypomnienia)',
    smsForwarderLimit: 'Limit ręcznych SMS spedytora na kontener dziennie',
  },
  en: {
    smsSettingsTab: 'Driver SMS', smsSaved: 'SMS settings saved.',
    smsSettingsHint: 'Delivery reminders sent automatically to drivers (Polish time).',
    smsReminderEnabled: 'Send reminders', smsReminderHour: 'Send hour (0–23)',
    smsReminderDays: 'Days before delivery (e.g. "2, 1" = two reminders)',
    smsForwarderLimit: 'Forwarder manual SMS limit per container per day',
  },
  pt: {
    smsSettingsTab: 'SMS aos motoristas', smsSaved: 'Definições de SMS guardadas.',
    smsSettingsHint: 'Lembretes de entrega enviados automaticamente aos motoristas (hora polaca).',
    smsReminderEnabled: 'Enviar lembretes', smsReminderHour: 'Hora de envio (0–23)',
    smsReminderDays: 'Dias antes da entrega (ex. "2, 1" = dois lembretes)',
    smsForwarderLimit: 'Limite de SMS manuais do transitário por contentor por dia',
  },
})
