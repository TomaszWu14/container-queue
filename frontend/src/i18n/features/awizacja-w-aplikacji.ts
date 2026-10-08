import { defineFeature } from '../feature'

// Awizacja w aplikacji — spedytor z kontem zamiast linku z maila (2026-10-07)
export default defineFeature({
  pl: {
    myAvizosPropose: 'Zaproponuj inny termin', myAvizosProposed: 'Propozycja wysłana do logistyki',
    myAvizosNewDate: 'Nowa data', myAvizosNewTime: 'Godzina', myAvizosSend: 'Wyślij propozycję',
    myAvizosTitle: 'Moje awizacje', myAvizosNone: 'Brak awizacji czekających na odpowiedź.',
    myAvizosHint: 'Potwierdź terminy i sloty, potem podaj dane kierowców — bez linku z maila.',
    myAvizosContainers: 'Kontenery', myAvizosConfirm: 'Potwierdź terminy',
    myAvizosDrivers: 'Podaj kierowców', myAvizosWaiting: 'Czeka na logistykę',
  },
  en: {
    myAvizosPropose: 'Propose another date', myAvizosProposed: 'Proposal sent to logistics',
    myAvizosNewDate: 'New date', myAvizosNewTime: 'Time', myAvizosSend: 'Send proposal',
    myAvizosTitle: 'My bookings', myAvizosNone: 'No bookings waiting for your answer.',
    myAvizosHint: 'Confirm dates and slots, then enter driver details — no e-mail link needed.',
    myAvizosContainers: 'Containers', myAvizosConfirm: 'Confirm dates',
    myAvizosDrivers: 'Enter drivers', myAvizosWaiting: 'Waiting for logistics',
  },
  pt: {
    myAvizosPropose: 'Propor outra data', myAvizosProposed: 'Proposta enviada à logística',
    myAvizosNewDate: 'Nova data', myAvizosNewTime: 'Hora', myAvizosSend: 'Enviar proposta',
    myAvizosTitle: 'As minhas marcações', myAvizosNone: 'Sem marcações à espera de resposta.',
    myAvizosHint: 'Confirme datas e horários e depois os dados dos motoristas — sem link de e-mail.',
    myAvizosContainers: 'Contentores', myAvizosConfirm: 'Confirmar datas',
    myAvizosDrivers: 'Indicar motoristas', myAvizosWaiting: 'À espera da logística',
  },
})
