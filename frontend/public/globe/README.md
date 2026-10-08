# Tekstury globusa (/sledzenie, widok 3D)

## earth-blue-marble-4k.webp

- **Źródło:** NASA Visible Earth — *Blue Marble: Next Generation w/ Topography and Bathymetry*,
  grudzień 2004 (`world.topo.bathy.200412.3x5400x2700.jpg`),
  https://visibleearth.nasa.gov/images/73909/december-blue-marble-next-generation-w-topography-and-bathymetry
- **Autor:** Reto Stöckli, NASA Earth Observatory (dane: NASA Goddard Space Flight Center).
- **Licencja:** domena publiczna — materiały NASA nie są chronione prawem autorskim
  i mogą być używane komercyjnie (https://www.nasa.gov/nasa-brand-center/images-and-media/).
  Nie wolno sugerować poparcia NASA ani używać logo NASA.
- **Obróbka:** przeskalowanie 5400×2700 → 4096×2048 (Lanczos) i kompresja WebP q80
  (~640 KB; limit pre-commit to 1024 KB/plik). Projekcja equirectangular, lon −180…180.

Maska połysku oceanu (specular) nie jest plikiem — generowana w przeglądarce z konturów
lądu (`LAND_PATH`, Natural Earth przez world-atlas, domena publiczna).

## tiles/ (ostre zbliżenia mapy 2D i globusa 3D)

Piramida kafelków z tego samego zdjęcia NASA w pełnej rozdzielczości
(`world.topo.bathy.200412.3x21600x10800.jpg`, ~30 MB, domena publiczna — **nie commitujemy go**),
układ `tiles/<z>/<wiersz>_<kolumna>.webp`, WebP q72, każdy plik < 200 KB (limit pre-commit 1024 KB):

| poziom | świat (px) | kafelki | px kafelka | rozmiar |
|---|---|---|---|---|
| z1 | 8192×4096 | 8×4 | 1024 | ~1,8 MB |
| z2 | 16384×8192 | 16×8 | 1024 | ~6 MB |
| z3 | 32768×16384 (nominalnie) | 32×16 | **675 (natywne źródło)** | ~11 MB |

z3 nie jest upscalowany: kafelek to natywne 21600/32 = 675 px źródła, a GPU/SVG rozciąga go na
1/32 świata — źródło nie ma więcej szczegółu (21600 px = ~60 px/°, 5,3× więcej niż zdjęcie 4k).

Kto używa: mapa 2D (`earthTiles.ts`, poziom wg szerokości ekranu × devicePixelRatio) i globus 3D
(`globeTiles.ts`, łaty sfery tylko w kadrze, max 4 wczytania naraz, zwalniane poza kadrem).
Wszystko lokalnie z `public/` — bez zewnętrznych serwerów kafelków (sieć firmowa).

Odtworzenie: pobierz źródło z
https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73909/world.topo.bathy.200412.3x21600x10800.jpg
i uruchom `python scripts/make_map_tiles.py <źródło.jpg> frontend/public/globe [poziomy, np. 3]` (Pillow).

Granice państw: world-atlas `countries-50m` (Natural Earth, domena publiczna) — na globusie jako
linie 3D (`globeBorders.ts`), na mapie 2D jako ścieżki SVG.

## relief/ (mapa terenu — domyślny wygląd mapy 2D i globusa od 2026-10-01)

- **Źródło:** Natural Earth *Shaded Relief* 1:10m, wersja HR (`SR_HR.tif`, 21600×10800, ~44 MB zip),
  https://www.naturalearthdata.com/downloads/10m-raster-data/10m-shaded-relief/ — **nie commitujemy go**.
- **Licencja:** domena publiczna (Natural Earth, https://www.naturalearthdata.com/about/terms-of-use/).
- **Obróbka:** `python scripts/make_map_tiles.py --relief SR_HR.tif frontend/public/globe/relief` —
  szarość terenu płaskiego/morza (206) przesunięta na 128 (neutralna dla mieszania hard-light),
  kontrast ×1,6; `relief-4k.webp` (4096×2048, ~0,3 MB) + `tiles/1` (8×4, ~1,4 MB) + `tiles/2`
  (16×8, ~5 MB), WebP q68, każdy plik < 300 KB. Razem ~6,6 MB.

Kto używa: `reliefTiles.ts` — mapa 2D (obrazy SVG z `mix-blend-mode: hard-light`) i globus
(tekstura terenu całej kuli 8192 px + łata regionu w rozdzielczości ekranu, `globeVector.ts`).
Kolory lądu/morza/państw z tokenów `--map-vec-*` (oba motywy), siła rzeźby `--map-vec-relief`.
Zdjęcie NASA (wyżej) jest już tylko opcjonalną warstwą „Zdjęcie satelitarne".
