import { defineFeature } from '../feature'

// SEC-006: obowiązkowe 2FA dla administratorów — ekran po zalogowaniu (Enroll2FAPage)
export default defineFeature({
  pl: {
    enroll2faTitle: 'Włącz uwierzytelnianie dwuskładnikowe',
    enroll2faInfo: 'Konto administratora wymaga 2FA. Do czasu włączenia możesz tylko przeglądać dane — zmiany są zablokowane.',
    enroll2faContinue: 'Zapisałem kody — przejdź do panelu',
  },
  en: {
    enroll2faTitle: 'Enable two-factor authentication',
    enroll2faInfo: 'Administrator accounts require 2FA. Until it is enabled you can only view data — changes are blocked.',
    enroll2faContinue: 'I saved the codes — go to the app',
  },
  pt: {
    enroll2faTitle: 'Ative a autenticação de dois fatores',
    enroll2faInfo: 'As contas de administrador exigem 2FA. Até a ativar, só pode consultar dados — as alterações estão bloqueadas.',
    enroll2faContinue: 'Guardei os códigos — ir para a aplicação',
  },
})
