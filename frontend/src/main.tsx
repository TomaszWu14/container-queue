import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
// design system: IBM Plex Sans 400/500/600 + Plex Mono 400/600 (fontsource: font-display: swap);
// grubości 700–900 i Mono 500 mapuje 00-fonts.css na prawdziwe kroje (bez sztucznego pogrubienia)
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/600.css'
import './styles/00-fonts.css'
import './styles/00-tokens.css'
// dawny styles.css podzielony na pliki ≤500 linii — kolejność = kaskada, nie zmieniaj
import './styles/01-tokens-base.css'
import './styles/02-queue-toolbar-rows.css'
import './styles/03-queue-company-grid.css'
import './styles/04-tracking-avizo-menus.css'
import './styles/05-status-pages.css'
import './styles/06-sidebar-nav.css'
import './styles/07-calendar-queue-week.css'
import './styles/08-feedback-tools.css'
import './styles/09-modules-rail-header.css'
import './styles/10-calendar-awizacji.css'
import './styles/11-kolejka-enterprise.css'
import './styles/12-kolejka-szuflada.css'
import './styles/13-kolejka-zakladki.css'
import './styles/14-kolejka-odchudzenie.css'
import './styles/15-kolory.css'
import './styles/16-obecnosc.css'
import './styles/17-filtry-kolumn.css'
import './styles/18-wdrozenie.css'
import './styles/19-kolejnosc-kolumn.css'
import './styles/20-kafelki-dokumentow.css'
import './styles/21-aktualnosci.css'
import './styles/22-wzory-agencji.css'
import './styles/23-podglad-maila.css'
import './tailwind.css'
import { applyTheme, getStoredTheme } from './theme'
import { installErrorBeacon } from './clientError'
import { installDateInputGuard } from './dates'
import { installChunkReload } from './chunkReload'

applyTheme(getStoredTheme()) // przed renderem — bez FOUC
installErrorBeacon()         // globalny beacon błędów (onerror + unhandledrejection)
installDateInputGuard()      // pola daty: niedopisany rok (0002) nie odpala akcji; „26” → 2026
installChunkReload()         // po wdrożeniu brak starego chunku → jednorazowe przeładowanie

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
