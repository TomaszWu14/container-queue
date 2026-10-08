// Zdjęcie NASA Blue Marble (equirectangular, lon −180…180) — wspólne dla globusa i mapy 2D;
// lokalny plik (public/globe), więc działa w sieci firmowej bez internetu.
// Osobny moduł (nie worldmap.ts): testy stron mockują worldmap w całości.
export const EARTH_PHOTO_URL = `${import.meta.env.BASE_URL}globe/earth-blue-marble-4k.webp`
