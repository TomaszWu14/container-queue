// SEC-004: backend odrzuca zapis z ciasteczkiem sesji bez tego nagłówka (chyba że Origin
// to nasz adres). Obca strona nie doda go bez preflightu CORS — dokładamy go do KAŻDEGO
// żądania do /api, także surowych fetch-ów (logowanie, odświeżenie sesji, beacon błędów).
// Osobny moduł (nie api.ts): testy często mockują './api' w całości.
export const CSRF_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const
