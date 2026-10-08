// Ekran w trakcie wdrożenia nowej wersji + pasek „nowa wersja” (DeployWatch.tsx)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    deployTitle: 'Trwa wgrywanie nowej wersji',
    deployWait: 'Proszę chwilę poczekać — strona odświeży się sama, gdy aplikacja wróci.',
    deployLong: 'Przerwa trwa dłużej niż zwykle. Jeśli nadal nie działa, prosimy o kontakt:',
    deployNewVersion: 'Jest nowa wersja aplikacji.', deployRefresh: 'Odśwież',
  },
  en: {
    deployTitle: 'A new version is being installed',
    deployWait: 'Please wait a moment — the page will reload by itself when the app is back.',
    deployLong: 'The break is taking longer than usual. If it still does not work, please contact:',
    deployNewVersion: 'A new version of the app is available.', deployRefresh: 'Refresh',
  },
  pt: {
    deployTitle: 'A instalar uma nova versão',
    deployWait: 'Aguarde um momento — a página recarrega sozinha quando a aplicação voltar.',
    deployLong: 'A pausa está a demorar mais do que o normal. Se continuar sem funcionar, contacte:',
    deployNewVersion: 'Há uma nova versão da aplicação.', deployRefresh: 'Atualizar',
  },
})
