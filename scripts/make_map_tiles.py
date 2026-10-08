"""Tnie NASA Blue Marble (equirectangular 21600x10800, lon -180..180) na piramidę kafelków WebP.

Układ: tiles/<z>/<y>_<x>.webp, kafelek TILE px. Poziom z ma szerokość BASE * 2**z
(z=1: 8192x4096 → 8x4 kafelki, z=2: 16384x8192 → 16x8, z=3: 32768x16384 → 32x16).
z=3 NIE jest upscalowany: kafelek ma natywne 21600/32 = 675 px źródła (GPU/SVG rozciąga go
na 1/32 świata) — więcej szczegółu źródło nie ma, a pliki są ~2× mniejsze. Poziom 0 to istniejący
frontend/public/globe/earth-blue-marble-4k.webp (nie generujemy go tutaj).

Użycie: python scripts/make_map_tiles.py world.topo.bathy.200412.3x21600x10800.jpg frontend/public/globe [poziomy, np. 3]

Tryb --relief (mapa terenu, 2026-10-01): cieniowana rzeźba Natural Earth SR_HR (21600x10800, domena
publiczna, naturalearthdata.com) → frontend/public/globe/relief: relief-4k.webp + kafelki z1..z2.
Płaski teren i morze mają w SR_HR wartość 206 — przesuwamy ją na 128 (neutralna szarość dla
mieszania hard-light), więc rzeźba nie wymaga maski lądu. Rzeźba jest niskoczęstotliwościowa,
gładkie powiększenie wygląda naturalnie → z3 (natywny) pomijamy, oszczędzając MB w repo.
    python scripts/make_map_tiles.py --relief SR_HR.tif frontend/public/globe/relief
"""
import pathlib
import sys

from PIL import Image

Image.MAX_IMAGE_PIXELS = None
TILE = 1024
LEVELS = (1, 2, 3)
NATIVE_FROM = 3   # od tego poziomu źródło jest za małe na 1024 px/kafelek → tniemy natywnie
QUALITY = 72


def main(src: str, out: str, only: tuple[int, ...] = LEVELS) -> None:
    img = Image.open(src).convert("RGB")
    for z in only:
        cols = 4 * 2 ** z
        if z >= NATIVE_FROM:
            level, tile = img, img.width // cols
        else:
            level, tile = img.resize((cols * TILE, cols * TILE // 2), Image.LANCZOS), TILE
        for y in range(cols // 2):
            for x in range(cols):
                path = pathlib.Path(out, "tiles", str(z), f"{y}_{x}.webp")
                path.parent.mkdir(parents=True, exist_ok=True)
                level.crop((x * tile, y * tile, (x + 1) * tile, (y + 1) * tile)) \
                    .save(path, "WEBP", quality=QUALITY, method=6)
        print(f"z={z}: {cols}x{cols // 2} kafelków po {tile} px")


RELIEF_FLAT = 206      # wartość płaskiego terenu/morza w SR_HR
RELIEF_GAIN = 1.6      # wzmocnienie kontrastu stoków wokół neutralnej szarości
RELIEF_QUALITY = 68


def relief(src: str, out: str) -> None:
    img = Image.open(src).convert("L").point(
        lambda v: max(0, min(255, round(128 + (v - RELIEF_FLAT) * RELIEF_GAIN))))
    img.resize((4096, 2048), Image.LANCZOS).save(pathlib.Path(out, "relief-4k.webp"), "WEBP",
                                                  quality=RELIEF_QUALITY, method=6)
    for z in (1, 2):
        cols = 4 * 2 ** z
        level = img.resize((cols * TILE, cols * TILE // 2), Image.LANCZOS)
        for y in range(cols // 2):
            for x in range(cols):
                path = pathlib.Path(out, "tiles", str(z), f"{y}_{x}.webp")
                path.parent.mkdir(parents=True, exist_ok=True)
                level.crop((x * TILE, y * TILE, (x + 1) * TILE, (y + 1) * TILE))                     .save(path, "WEBP", quality=RELIEF_QUALITY, method=6)
        print(f"rzeźba z={z}: {cols}x{cols // 2} kafelków")


if __name__ == "__main__":
    if sys.argv[1] == "--relief":
        relief(sys.argv[2], sys.argv[3])
        sys.exit()
    main(sys.argv[1], sys.argv[2], tuple(map(int, sys.argv[3:])) or LEVELS)
