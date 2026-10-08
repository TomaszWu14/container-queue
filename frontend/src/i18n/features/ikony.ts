import { defineFeature } from '../feature'

// Nazwy przycisków ikonowych (audyt UI PR 6) — ‹ › same w sobie nic nie mówią czytnikowi
export default defineFeature({
  pl: { pagePrev: 'Poprzednia strona', pageNext: 'Następna strona', weekPrev: 'Poprzedni tydzień', weekNext: 'Następny tydzień' },
  en: { pagePrev: 'Previous page', pageNext: 'Next page', weekPrev: 'Previous week', weekNext: 'Next week' },
  pt: { pagePrev: 'Página anterior', pageNext: 'Página seguinte', weekPrev: 'Semana anterior', weekNext: 'Semana seguinte' },
})
