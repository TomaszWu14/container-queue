import { defineFeature } from '../feature'

// Menu użytkownika (audyt UI C25, UX-043): podpisane pozycje zamiast samych ikon
export default defineFeature({
  pl: {
    umWatchOnly: 'Powiadomienia tylko o obserwowanych', umLanguage: 'Język',
    umTheme: 'Motyw: {mode}', umThemeDark: 'ciemny', umThemeLight: 'jasny',
  },
  en: {
    umWatchOnly: 'Notifications for watched only', umLanguage: 'Language',
    umTheme: 'Theme: {mode}', umThemeDark: 'dark', umThemeLight: 'light',
  },
  pt: {
    umWatchOnly: 'Notificações só dos seguidos', umLanguage: 'Idioma',
    umTheme: 'Tema: {mode}', umThemeDark: 'escuro', umThemeLight: 'claro',
  },
})
