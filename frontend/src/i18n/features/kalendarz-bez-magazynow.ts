import { defineFeature } from '../feature'

// Kalendarz bez magazynów z limitem awizacji: jeden komunikat zamiast siatki „0 /0” (audyt UI C9)
export default defineFeature({
  pl: {
    calNoCapacityTitle: 'Brak skonfigurowanych magazynów i limitów awizacji',
    calNoCapacityHint: 'Obłożenie liczy się z dziennych limitów magazynów, do których w tym roku są awizacje. Żaden magazyn nie ma jeszcze awizacji ani limitu.',
    calNoCapacityLink: 'Ustaw magazyny i limity',
  },
  en: {
    calNoCapacityTitle: 'No warehouses or booking limits configured',
    calNoCapacityHint: 'Utilisation is based on the daily limits of warehouses with bookings this year. No warehouse has bookings or a limit yet.',
    calNoCapacityLink: 'Set up warehouses and limits',
  },
  pt: {
    calNoCapacityTitle: 'Sem armazéns nem limites de marcação configurados',
    calNoCapacityHint: 'A ocupação calcula-se a partir dos limites diários dos armazéns com marcações este ano. Nenhum armazém tem ainda marcações nem limite.',
    calNoCapacityLink: 'Configurar armazéns e limites',
  },
})
