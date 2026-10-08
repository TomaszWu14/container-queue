"""Pakowanie kartonów do kontenera — reguła: najpierw bloki mono-SKU, resztki mieszane.

Reguła magazynowa: najpierw pełne bloki mono-SKU (jeden SKU nigdy nie jest
rozproszony po kontenerze), dopiero resztki idą do wspólnej puli mieszanej
pakowanej py3dbp. Wymiary kartonów z MARM (MaterialUnit.dims_cm); brak wymiarów
a jest objętość -> sześcian `approximated`; brak wszystkiego -> `excluded`.

Wszystkie wymiary w cm; oś X = długość kontenera, Y = wysokość, Z = szerokość.
"""
import math
import zlib

from ..models.typed_text import quantity_value
from ..serializers import marm_volume_m3

# Wnętrza typów kontenerów (cm) — fallback, gdy słownikowy ContainerType nie ma
# kompletu wymiarów wewnętrznych (typ dodany ręcznie bez danych).
_FALLBACK_DIMS = {"20": (589.0, 235.0, 239.0),
                  "40": (1203.0, 235.0, 239.0),
                  "40HC": (1203.0, 235.0, 269.0)}

# ponytail: limit kartonów w wizualizacji — SKU ponad
# limit ląduje w excluded zamiast kłaść przeglądarkę; podnieś gdy zajdzie potrzeba
MAX_BOXES = 2000

# ponad tyle kartonów w puli mieszanej py3dbp robi się nieużywalnie wolny (~sześcienny);
# większa pula -> deterministyczne plastry per SKU (patrz krok 3)
PY3DBP_POOL_CAP = 150


def container_inner_dims_cm(container_type) -> tuple[float, float, float] | None:
    """Wymiary wnętrza (L, W, H) w cm ze słownika ContainerType, z fallbackiem
    na stałe wg nazwy (20' / 40' / 40'HC). None = typ nieznany bez wymiarów."""
    if container_type is None:
        return None
    if (container_type.inner_length_m and container_type.inner_width_m
            and container_type.inner_height_m):
        return (float(container_type.inner_length_m) * 100,
                float(container_type.inner_width_m) * 100,
                float(container_type.inner_height_m) * 100)
    name = (container_type.name or "").upper()
    if "40" in name and "HC" in name:
        return _FALLBACK_DIMS["40HC"]
    if "40" in name:
        return _FALLBACK_DIMS["40"]
    if "20" in name:
        return _FALLBACK_DIMS["20"]
    return None


def _sku_color(sku: str) -> str:
    """Deterministyczny kolor per SKU (stały między requestami i sesjami)."""
    hue = zlib.crc32(sku.encode()) % 360
    # HSL -> RGB w wąskim pasie nasyceń/jasności, żeby paleta była czytelna
    c, x = 0.55, 0.55 * (1 - abs((hue / 60) % 2 - 1))
    m = 0.62 - 0.55 / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][hue // 60]
    return "#%02x%02x%02x" % tuple(round((v + m) * 255) for v in (r, g, b))


def _sku_dims(item, rows) -> tuple[tuple[float, float, float] | None, bool, str]:
    """Wymiary pojedynczego kartonu (cm) dla pozycji: z MARM wprost albo sześcian
    z objętości (approximated). Zwraca (dims | None, approximated, powód braku)."""
    unit = (item.unit or "").upper()
    direct = next((r for r in rows if r.unit == unit), None)
    if direct is not None:
        dims = direct.dims_cm()
        if dims:
            return dims, False, ""
    vol_m3 = marm_volume_m3(1, unit, rows) if rows else None
    if vol_m3 and vol_m3 > 0:
        side = round((vol_m3 * 1_000_000) ** (1 / 3), 1)
        return (side, side, side), True, ""
    return None, False, "brak danych MARM (wymiarów i objętości)"


class _Packing:
    """Stan układania kontenera (CODE-004: 3 fazy jako osobne funkcje): kartony, wykluczenia,
    kursor wzdłuż długości, licznik kartonów i objętość zapotrzebowania."""

    def __init__(self, dims_cm: tuple[float, float, float]):
        self.L, self.W, self.H = dims_cm
        self.boxes: list[dict] = []
        self.excluded: list[dict] = []
        self.cursor_x = 0.0
        self.total_boxes = 0
        self.demanded_cm3 = 0.0

    def box(self, g: dict, x, y, z, l, w, h) -> None:
        self.boxes.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1),
                           "w": round(l, 1), "h": round(h, 1), "d": round(w, 1),
                           "sku": g["sku"], "color": g["color"],
                           "approximated": g["approximated"]})

    def exclude(self, g: dict, reason: str) -> None:
        self.excluded.append({"order_no": g["order_no"], "material": g["sku"], "reason": reason})


def _sku_groups(items, material_rows: dict[str, list], excluded: list[dict]) -> list[dict]:
    """1. Pozycje -> grupy SKU (ilość × wymiary kartonu); śmieciowe wiersze -> excluded.
    Kolejność: największa objętość grupy najpierw, potem SKU."""
    by_key: dict[tuple, dict] = {}
    for item in items:
        qty = quantity_value(getattr(item, "quantity_num", None), item.quantity)   # DB-008
        if qty is None or qty <= 0:
            excluded.append({"order_no": item.order_number, "material": item.material,
                             "reason": "nieprawidłowa ilość"})
            continue
        rows = material_rows.get(item.material) or []
        dims, approximated, reason = _sku_dims(item, rows)
        if dims is None:
            excluded.append({"order_no": item.order_number, "material": item.material,
                             "reason": reason})
            continue
        key = (item.material, dims)
        group = by_key.setdefault(key, {
            "sku": item.material, "dims": dims, "qty": 0, "order_no": item.order_number,
            "approximated": approximated, "color": _sku_color(item.material)})
        group["qty"] += math.ceil(qty)
    return sorted(by_key.values(),
                  key=lambda g: (-(g["qty"] * g["dims"][0] * g["dims"][1] * g["dims"][2]),
                                 g["sku"]))


def _place_blocks(p: _Packing, groups: list[dict]) -> list[dict]:
    """2. Bloki mono-SKU: pełne plastry przekroju W×H wzdłuż długości. Zwraca resztki
    (pojedyncze kartony) do puli mieszanej."""
    pool: list[dict] = []
    for g in groups:
        l, w, h = g["dims"]
        n = g["qty"]
        if p.total_boxes + n > MAX_BOXES:
            p.exclude(g, f"limit wizualizacji ({MAX_BOXES} kartonów)")
            continue
        # orientacja stopy maksymalizująca przekrój (dozwolony obrót 90°)
        if w <= p.W and l <= p.W and p.W // l > p.W // w:
            l, w = w, l
        nz, ny = int(p.W // w), int(p.H // h)
        per_slice = nz * ny
        if per_slice < 1 or l > p.L:   # karton nie mieści się w przekroju kontenera
            p.exclude(g, "karton większy niż wnętrze kontenera")
            continue
        p.total_boxes += n
        p.demanded_cm3 += n * l * w * h
        max_slices = int((p.L - p.cursor_x) // l)
        full = min(n // per_slice, max_slices)
        for s in range(full):
            for yi in range(ny):
                for zi in range(nz):
                    if s * per_slice + yi * nz + zi >= n:
                        break
                    p.box(g, p.cursor_x + s * l, yi * h, zi * w, l, w, h)
        placed = full * per_slice
        p.cursor_x += full * l
        for _ in range(n - placed):
            pool.append({**g, "dims": (l, w, h)})
    return pool


def _place_pool_slices(p: _Packing, pool: list[dict]) -> None:
    """3a. Duża pula: deterministyczne plastry per SKU (py3dbp byłby zbyt wolny)."""
    slots: dict[str, dict] = {}   # stan plastrów per SKU
    for g in sorted(pool, key=lambda item: item["sku"]):
        l, w, h = g["dims"]
        nz, ny = int(p.W // w), int(p.H // h)
        slot = slots.setdefault(g["sku"], {"x": None, "i": 0})
        if slot["x"] is None or slot["i"] >= nz * ny:
            if p.cursor_x + l > p.L:
                p.exclude(g, "nie zmieściło się")
                continue
            slot["x"], slot["i"] = p.cursor_x, 0
            p.cursor_x += l
        yi, zi = slot["i"] // nz, slot["i"] % nz
        p.box(g, slot["x"], yi * h, zi * w, l, w, h)
        slot["i"] += 1


def _place_pool_py3dbp(p: _Packing, pool: list[dict]) -> None:
    """3b. Mała pula: py3dbp w pozostałej przestrzeni (bigger_first)."""
    from py3dbp import Bin, Item, Packer
    packer = Packer()
    packer.add_bin(Bin("rest", p.L - p.cursor_x, p.H, p.W, 10 ** 9))
    meta = {}
    for i, g in enumerate(sorted(pool, key=lambda item: item["sku"])):
        name = str(i)
        meta[name] = g
        l, w, h = g["dims"]
        packer.add_item(Item(name, l, h, w, 1))   # (w=x, h=y, d=z)
    packer.pack(bigger_first=True, number_of_decimals=1)
    bin_ = packer.bins[0]
    for it in bin_.items:
        l, h, w = (float(v) for v in it.get_dimension())
        px, py, pz = (float(v) for v in it.position)
        p.box(meta[it.name], p.cursor_x + px, py, pz, l, w, h)
    for it in bin_.unfitted_items:
        p.exclude(meta[it.name], "nie zmieściło się")


def pack_container(items, dims_cm: tuple[float, float, float],
                   material_rows: dict[str, list]) -> dict:
    """Ułóż pozycje kontenera w jego wnętrzu. `items` = OrderItem-y, `material_rows`
    = mapa material_no -> wiersze MaterialUnit. Zwraca JSON wg specu."""
    p = _Packing(dims_cm)
    groups = _sku_groups(items, material_rows, p.excluded)
    pool = _place_blocks(p, groups)
    # 3. Pula mieszana. ponytail: py3dbp jest ~sześcienny (150 kartonów ≈ 2 s, 600 ≈ minuty)
    # — większa pula idzie deterministycznym układaniem plastrów per SKU zamiast optymalizatora
    if pool and p.cursor_x < p.L:
        (_place_pool_slices if len(pool) > PY3DBP_POOL_CAP else _place_pool_py3dbp)(p, pool)
    else:
        for g in pool:
            p.exclude(g, "nie zmieściło się")

    L, W, H = dims_cm
    volume_total = L * W * H / 1_000_000
    # objętość ZAPOTRZEBOWANIA (bloki + pula, także niezmieszczone) — >100% = przepełnienie
    demanded = p.demanded_cm3 / 1_000_000
    return {
        "status": "ok" if p.boxes else "no_data",
        "boxes": p.boxes,
        "fill_pct": round(demanded / volume_total * 100, 1) if volume_total else 0.0,
        "volume_used_m3": round(demanded, 2),
        "volume_total_m3": round(volume_total, 2),
        "container_dims": {"l": L, "w": W, "h": H},
        "excluded": p.excluded,
    }
