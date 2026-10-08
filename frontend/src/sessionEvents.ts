// Nazwa zdarzenia „sesja wygasła” (api.ts → App) w osobnym module: testy mockujące './api'
// nie muszą jej powielać, a App nie zależy od mocka klienta HTTP.
export const SESSION_EXPIRED_EVENT = 'timporye:session-expired'
