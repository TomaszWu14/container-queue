"""Wykrywa duplikaty w słownikach (porty, dostawcy, armatorzy) i proponuje scalenia.

Import z Excela nawiózł warianty tej samej nazwy: SHANGHAI / Shanghai / shangai,
FUNSHIDE / FUSHIDE / Funshide. Do każdego wariantu są podpięte kontenery, więc samo
przemianowanie ich nie scali — trzeba przepiąć powiązania.

Skrypt NIGDY nie zmienia danych bez zatwierdzenia. Dwa kroki:

  1. python scripts/dedupe_dictionaries.py                 → raport + plan do pliku JSON
  2. python scripts/dedupe_dictionaries.py --apply plan.json  → wykonanie (z potwierdzeniem)

Plan jest zwykłym JSON-em: PRZEJRZYJ GO i wykreśl wszystko, czego nie chcesz scalać.
Scalenia „pewne” (identyczne po normalizacji) i „do przejrzenia” (podobne, np.
DEMMO/DEMO MEDICAL) są rozdzielone — te drugie wymagają Twojej decyzji, bo skrypt
nie odróżni literówki od dwóch różnych firm.

PRZED --apply na produkcji zrób backup: sh scripts/backup.sh
"""
import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app import audit  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.routers.dictionaries import CARRIERS, PORTS, _Dict  # noqa: E402

# próg podobieństwa dla „do przejrzenia”: 0.85 łapie DEMMO/DEMO i NORTBRIDGE/NORTHBRIDGE,
# a nie skleja Ningbo z Ningde. Dobrane empirycznie na danych z importu.
SIMILARITY = 0.85

# dostawcy: scripts/consolidate_suppliers.py (kartoteka globalna, scalanie po kodzie SAP)
SPECS = {"ports": PORTS, "carriers": CARRIERS}


def normalize(name: str) -> str:
    """Wspólna postać do porównań: bez wielkości liter, spacji i znaków ozdobnych."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def canonical_score(name: str, usage: int) -> tuple:
    """Kandydat na rekord docelowy: najpierw ŁADNIEJ ZAPISANY, dopiero potem liczba użyć.

    Kolejność jest tu istotna. Gdyby wygrywała liczba użyć, celem zostawałaby wersalikowa
    wklejka z Excela ('NINGBO', 42 użycia) zamiast nazwy z master daty ('Ningbo'), i całe
    sprzątanie zamieniłoby słownik w WERSALIKI — odwrotnie do celu. Liczba użyć rozstrzyga
    dopiero remisy. Nie podoba się wybór? Podmień "target" w planie JSON przed --apply.
    """
    is_clean = not name.isupper() and not name.islower()   # 'Shanghai' tak, 'SHANGHAI'/'shangai' nie
    return (is_clean, usage, -len(name))


def load_entries(db, spec: _Dict) -> list[dict]:
    """Wpisy słownika wraz z liczbą powiązań (ile rekordów na nie wskazuje)."""
    entries = []
    for item in db.scalars(select(spec.model)).all():
        usage = sum(
            db.scalar(select(func.count()).select_from(model)
                      .where(getattr(model, column) == item.id))
            for model, column in spec.refs
        )
        entry = {"id": item.id, "name": item.name, "usage": usage}
        entries.append(entry)
    return entries


def group_key(entry: dict, spec: _Dict) -> tuple:
    return (normalize(entry["name"]),)


def propose(entries: list[dict], spec: _Dict) -> tuple[list[dict], list[dict]]:
    """Zwraca (pewne, do_przejrzenia) — grupy identyczne po normalizacji i tylko podobne."""
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for entry in entries:
        buckets[group_key(entry, spec)].append(entry)

    certain, review = [], []
    for group in buckets.values():
        if len(group) > 1:
            certain.append(_merge_group(group))

    # podobne, ale nieidentyczne — literówki. Porównujemy tylko reprezentantów grup,
    # żeby nie proponować scalania z rekordem, który i tak zniknie w scaleniu pewnym.
    leaders = [_merge_group(g)["target"] if len(g) > 1 else g[0] for g in buckets.values()]
    for i, a in enumerate(leaders):
        for b in leaders[i + 1:]:
            ratio = SequenceMatcher(None, normalize(a["name"]), normalize(b["name"])).ratio()
            if SIMILARITY <= ratio < 1.0:
                review.append(_merge_group([a, b]) | {"similarity": round(ratio, 3)})
    return certain, review


def _merge_group(group: list[dict]) -> dict:
    target = max(group, key=lambda e: canonical_score(e["name"], e["usage"]))
    sources = [e for e in group if e["id"] != target["id"]]
    return {"target": target, "sources": sources}


def report(db) -> dict:
    plan = {}
    for kind, spec in SPECS.items():
        entries = load_entries(db, spec)
        certain, review = propose(entries, spec)
        plan[kind] = {"certain": certain, "review": review}

        print(f"\n=== {kind.upper()} ({len(entries)} wpisów) ===")
        if not certain and not review:
            print("  czysto — brak duplikatów")
        for label, groups in (("PEWNE", certain), ("DO PRZEJRZENIA", review)):
            for group in groups:
                target, sources = group["target"], group["sources"]
                extra = f"  [podobieństwo {group['similarity']}]" if "similarity" in group else ""
                names = ", ".join(f"{s['name']!r} (id={s['id']}, użyć: {s['usage']})"
                                  for s in sources)
                # ASCII w wydruku: konsola Windows (cp1250) nie zakoduje strzałki unicode
                print(f"  [{label}]{extra}")
                print(f"    {names}")
                print(f"      -> {target['name']!r} (id={target['id']}, "
                      f"uzyc: {target['usage']})")
    return plan


def resolve_chains(pairs: list[tuple[int, int]]) -> dict[int, int]:
    """Spłaszcza łańcuchy scaleń: A→B i B→C muszą dać A→C, nie osierocone FK na skasowanym B.

    Powstają naturalnie, gdy grupa 'pewna' (FUNSHIDE→Funshide) spotyka się z 'do przejrzenia'
    (Funshide→FUSHIDE). Bez tego kolejność wykonania decydowałaby o poprawności danych.
    """
    target_of = dict(pairs)
    resolved = {}
    for source in target_of:
        seen, final = {source}, target_of[source]
        while final in target_of and final not in seen:
            seen.add(final)
            final = target_of[final]
        resolved[source] = final
    return resolved


def apply_plan(db, plan: dict) -> None:
    """Wykonuje scalenia z planu — tą samą logiką co endpoint (ta sama mapa FK)."""
    total = 0
    for kind, groups in plan.items():
        spec = SPECS[kind]
        # 'review' wykonujemy tylko wtedy, gdy zostało w pliku — to świadoma decyzja użytkownika
        all_groups = groups.get("certain", []) + groups.get("review", [])
        pairs = [(source["id"], group["target"]["id"])
                 for group in all_groups for source in group["sources"]]
        final_target = resolve_chains(pairs)

        for group in all_groups:
            for source in group["sources"]:
                source_id = source["id"]
                target_id = final_target[source_id]
                if target_id == source_id:
                    continue                     # cykl w planie — pomijamy, nie kasujemy
                repinned = {}
                for model, column in spec.refs:
                    result = db.execute(
                        model.__table__.update()
                        .where(getattr(model, column) == source_id)
                        .values(**{column: target_id}))
                    if result.rowcount:
                        repinned[model.__tablename__] = result.rowcount
                item = db.get(spec.model, source_id)
                target = db.get(spec.model, target_id)
                if item is None or target is None:
                    print(f"  ! pominieto id={source_id} - zrodlo lub cel juz nie istnieje")
                    continue
                # nazwa celu Z BAZY, nie z planu: po spłaszczeniu łańcucha cel bywa inny
                # niż zapisany w grupie, a audyt musi zgadzać się z tym, co faktycznie zaszło
                audit.record(db, entity_type=spec.model.__tablename__, entity_id=target_id,
                             field="merge", old_value=f"{item.name} (id={source_id})",
                             new_value=f"{target.name} (id={target_id})",
                             user=None, note=f"dedupe: przepięto {repinned or 'nic'}")
                db.delete(item)
                total += 1
                print(f"  scalono {item.name!r} -> {target.name!r}  {repinned or ''}")
    db.commit()
    print(f"\nGotowe: {total} scaleń.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", metavar="PLAN.JSON",
                        help="wykonaj scalenia z zatwierdzonego planu")
    parser.add_argument("--out", default="dedupe_plan.json",
                        help="dokąd zapisać plan (domyślnie: dedupe_plan.json)")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.apply:
            plan = json.loads(pathlib.Path(args.apply).read_text(encoding="utf-8"))
            groups = sum(len(g.get("certain", [])) + len(g.get("review", []))
                         for g in plan.values())
            print(f"Plan: {groups} grup do scalenia. To ZMIENI dane.")
            print("Zrobiłeś backup? (scripts/backup.sh)")
            if input('Wpisz "tak", aby kontynuować: ').strip().lower() != "tak":
                print("Przerwano — nic nie zmieniono.")
                return
            apply_plan(db, plan)
            return

        plan = report(db)
        pathlib.Path(args.out).write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nPlan zapisany: {args.out}")
        print("PRZEJRZYJ go (zwłaszcza sekcje 'review'), usuń niechciane grupy, potem:")
        print(f"  python scripts/dedupe_dictionaries.py --apply {args.out}")


if __name__ == "__main__":
    main()
