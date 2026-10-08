// Główny transport kontenera (do hubu/portu): morski / lotniczy — obok bazowych koła / kolej / inne
import { defineFeature } from '../feature'

export default defineFeature({
  pl: { transport_morski: 'morski', transport_lotniczy: 'lotniczy', mode_AIR: 'Lotniczy' },
  en: { transport_morski: 'sea', transport_lotniczy: 'air', mode_AIR: 'Air' },
  pt: { transport_morski: 'marítimo', transport_lotniczy: 'aéreo', mode_AIR: 'Aéreo' },
})
