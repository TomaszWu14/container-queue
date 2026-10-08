"""Podsumowanie syncu kolejki z Excela: jedno powiadomienie na przebieg."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import WatchedContainer
from ..notifications import company_watchers, notify

SUMMARY_LIST_MAX = 20


def _summary(results: list[dict]) -> tuple[str, str]:
    new = [r for r in results if r["changes"][0][0] == "__new__"]
    lines = [f"{r['container'].container_no}: "
             + ("nowy" if r["changes"][0][0] == "__new__" else ", ".join(f for f, _, _ in r["changes"]))
             for r in results[:SUMMARY_LIST_MAX]]
    if len(results) > SUMMARY_LIST_MAX:
        lines.append(f"… i {len(results) - SUMMARY_LIST_MAX} więcej")
    title = f"Sync z Excela: {len(results)} kontenerów zmienionych (w tym {len(new)} nowych)"
    return title, "\n".join(lines)


def _link(results: list[dict]) -> int | None:
    return results[0]["container"].id if len(results) == 1 else None   # 1 kontener → link


def notify_sync_summary(db: Session, company, results: list[dict]) -> int:
    """JEDNO powiadomienie na przebieg syncu (dawniej jedno na kontener — duży sync zalewał
    pocztę/Teams setkami wiadomości). Audyt per kontener zostaje w AuditLog. Zwraca liczbę
    kontenerów objętych wysłanym powiadomieniem (0 = nic nie poszło).

    Userzy z „tylko obserwowane” dostają własny wariant — wyłącznie ich obserwowane kontenery
    (żadnego, gdy nic z przebiegu nie obserwują); reszta pełne podsumowanie."""
    if not results:
        return 0
    users = company_watchers(db, company.id)
    picky = [u for u in users if u.watch_only_notifications]
    title, body = _summary(results)
    sent = notify(db, [u for u in users if not u.watch_only_notifications], kind="excel-sync",
                  title=title, body=body, container_id=_link(results))
    if picky:
        by_id = {r["container"].id: r for r in results}
        watched: dict[int, list[dict]] = {}
        for uid, cid in db.execute(select(WatchedContainer.user_id, WatchedContainer.container_id)
                                   .where(WatchedContainer.user_id.in_([u.id for u in picky]),
                                          WatchedContainer.container_id.in_(by_id))):
            watched.setdefault(uid, []).append(by_id[cid])
        for u in picky:
            mine = watched.get(u.id)
            if mine:
                t, b = _summary(mine)
                sent += notify(db, [u], kind="excel-sync", title=t, body=b,
                               container_id=_link(mine), broadcast=False)
    return len(results) if sent else 0
