# Obserwowanie PR 2 (awatar + miniatury na mapie) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Użytkownik wgrywa awatar w profilu; „Śledzone przez…" i mapa (2D) pokazują miniaturki obserwujących (awatar albo inicjały).

**Architecture:** `User.avatar` (nazwa pliku w `uploads/avatars/`), nowy router `routers/avatars.py` (upload/usuń/pobierz). Reguła „kto kogo widzi" wydzielona z `_watchers_out` do `can_see_watcher(viewer, target)` w `routers/watchers.py` i reużyta przez GET awatara oraz przez zbiorcze `watchers_by_target(...)`, które dokleja obserwujących do `/tracking/map` i `/tracking/vessels` jednym zapytaniem. Front: `<UserAvatar>` (HTML) i `<AvatarStack>` (SVG na mapie).

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic, React 19 + vitest. Mapa 2D to własny SVG (`frontend/src/pages/tracking/FlatMap.tsx`), obrazki ładowane przez cookies (bez nagłówka Authorization) — `<img src>` / SVG `<image href>` działają wprost.

Spec: `docs/superpowers/specs/2026-09-24-obserwowanie-kto-dlaczego-design.md` (sekcja PR 2). Bazuje na PR 1: `routers/watchers.py` z `_watchers_out`, `INTERNAL_ROLES`, `WatchedContainer`/`WatchedVessel`.

## Global Constraints

- Max 500 linii na plik (`scripts/check_file_lengths.py`); plików z BASELINE nie wydłużać.
- Migracja od jedynej głowy alembica (po PR 1: **`watch001`**; sprawdź `python -m alembic heads`).
- Nowe teksty UI tylko w `frontend/src/i18n/features/<funkcja>.ts` (`defineFeature`).
- Widoczność obserwujących i awatarów — JEDNA reguła `can_see_watcher(viewer, target)`:
  target == viewer → tak; viewer spoza `admin/logistics/purchasing` → nie;
  viewer z `can_view_all` → tak; inaczej tak tylko gdy `target.company_id == viewer.company_id` albo `can_view_all(target)`.
- Upload awatara: tylko obrazy (walidacja sygnatury `_looks_like_image` z `routers/complaints_common.py`), max **2 MB**, losowa nazwa pliku, stary plik usuwany, zapis przez `commit_with_file` (`routers/forwarding_files.py`), limit przez `read_upload_capped` (tamże).
- Mapa: max **3** awatary + „+n", bez N+1 (jedno zapytanie na obserwujących dla wszystkich punktów/statków).
- Przed PR: backend pełny pytest, `npx vitest run`, `npm run build`.

---

### Task 1: Awatar — model, migracja, API

**Files:**
- Modify: `backend/app/models/dictionaries.py` (klasa `User`: kolumna `avatar` + property `has_avatar`)
- Create: `backend/migrations/versions/avatar001_user_avatar.py`
- Modify: `backend/app/schemas/auth.py` (`UserOut.has_avatar: bool = False`) — sprawdź, gdzie jest `UserOut` (`grep -rn "class UserOut" backend/app/schemas`)
- Modify: `backend/app/routers/watchers.py` (wydzielenie `can_see_watcher`, `has_avatar` w odpowiedzi `/watchers`)
- Create: `backend/app/routers/avatars.py`
- Modify: `backend/app/main.py` (import + `include_router(avatars.router)` obok `watchers`)
- Test: `backend/tests/test_avatars.py`

**Interfaces:**
- Produces: `User.avatar: str`, `User.has_avatar: bool` (property); `can_see_watcher(viewer: User, target: User) -> bool` w `routers/watchers.py`; HTTP: `POST /api/me/avatar` (multipart `file`) → `{"has_avatar": true}`, `DELETE /api/me/avatar` → `{"has_avatar": false}`, `GET /api/users/{id}/avatar` → obraz / 404; `UserOut.has_avatar`; w `/watchers` każdy wpis ma `has_avatar`.

- [ ] **Step 1: Failing tests** — `backend/tests/test_avatars.py`:

```python
"""Awatar użytkownika: upload/usuń, walidacja, widoczność wg can_see_watcher."""
from app.database import SessionLocal
from app.models import Role, User
from app.security import hash_password
from tests.conftest import login

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _company_id(client, headers, code="ACME"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def _user(login_name, role, company_id):
    with SessionLocal() as db:
        u = User(login=login_name, hashed_password=hash_password("pass12345"), role=role,
                 company_id=company_id, view_all_companies=False, email="")
        db.add(u)
        db.commit()
        return u.id


def test_upload_get_delete_own_avatar(client):
    h = login(client)
    r = client.post("/api/me/avatar", headers=h, files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    assert r.json() == {"has_avatar": True}
    me = client.get("/api/auth/me", headers=h).json()
    assert me["has_avatar"] is True
    got = client.get(f"/api/users/{me['id']}/avatar", headers=h)
    assert got.status_code == 200 and got.content.startswith(b"\x89PNG")
    assert client.delete("/api/me/avatar", headers=h).json() == {"has_avatar": False}
    assert client.get(f"/api/users/{me['id']}/avatar", headers=h).status_code == 404


def test_rejects_non_image_and_too_big(client):
    h = login(client)
    r = client.post("/api/me/avatar", headers=h, files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 422
    big = PNG + b"\x00" * (2 * 1024 * 1024)
    r = client.post("/api/me/avatar", headers=h, files={"file": ("b.png", big, "image/png")})
    assert r.status_code == 413


def test_avatar_visibility_follows_watcher_rule(client):
    admin = login(client)
    acme = _company_id(client, admin)
    borealis = _company_id(client, admin, "BOREALIS")
    _user("logz", Role.logistics, acme)
    _user("logt", Role.logistics, borealis)
    _user("magz", Role.warehouse, acme)
    lz = login(client, "logz", "pass12345")
    lt_id = client.get("/api/auth/me", headers=login(client, "logt", "pass12345")).json()["id"]
    lt = login(client, "logt", "pass12345")
    client.post("/api/me/avatar", headers=lt, files={"file": ("a.png", PNG, "image/png")})

    # ta sama spółka / admin z widokiem wszystkich — widzi; inna spółka — nie
    assert client.get(f"/api/users/{lt_id}/avatar", headers=admin).status_code == 200
    assert client.get(f"/api/users/{lt_id}/avatar", headers=lz).status_code == 404
    # rola zewnętrzna nie widzi cudzych awatarów
    mz = login(client, "magz", "pass12345")
    assert client.get(f"/api/users/{lt_id}/avatar", headers=mz).status_code == 404
```

Sprawdź w `backend/app/routers/auth.py` ścieżkę `/me` (prefiks routera — `/api/auth/me` albo inny) i status zwracany przez `read_upload_capped` przy przekroczeniu limitu (413 czy 422) — dopasuj asercje do rzeczywistości, nie odwrotnie. Brak dostępu celowo 404 (nie ujawniamy istnienia usera/awatara).

- [ ] **Step 2: Run** `cd backend && python -m pytest -q tests/test_avatars.py` → FAIL.

- [ ] **Step 3: Model** — w klasie `User` (`backend/app/models/dictionaries.py`) dopisz:

```python
    # awatar: nazwa pliku w uploads/avatars/ (pusty = inicjały w UI)
    avatar: Mapped[str] = mapped_column(String(255), default="", server_default="")

    @property
    def has_avatar(self) -> bool:
        return bool(self.avatar)
```

- [ ] **Step 4: Migracja** `backend/migrations/versions/avatar001_user_avatar.py`:

```python
"""Awatar użytkownika (users.avatar — nazwa pliku w uploads/avatars/).

Revision ID: avatar001
Revises: watch001
"""
import sqlalchemy as sa
from alembic import op

revision = "avatar001"
down_revision = "watch001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("avatar", sa.String(255), nullable=False,
                                   server_default=sa.text("''")))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("avatar")
```

- [ ] **Step 5: `UserOut`** — dopisz pole `has_avatar: bool = False` (ORMModel z `from_attributes` czyta property).

- [ ] **Step 6: Reguła widoczności** — w `backend/app/routers/watchers.py` wydziel z `_watchers_out` funkcję i użyj jej w filtrze; dopisz `has_avatar` do wpisów:

```python
def can_see_watcher(viewer: User, target: User) -> bool:
    """Czy viewer widzi obserwującego/awatar targetu — jedna reguła dla /watchers, mapy i awatarów."""
    if target.id == viewer.id:
        return True
    if viewer.role not in INTERNAL_ROLES:
        return False
    if can_view_all(viewer):
        return True
    return target.company_id == viewer.company_id or can_view_all(target)
```

W `_watchers_out`: `rows = [(w, u) for w, u in rows if can_see_watcher(user, u)]` zamiast obecnych dwóch gałęzi; w słowniku wpisu dodaj `"has_avatar": u.has_avatar`. Istniejące testy `tests/test_watchers.py` muszą przejść bez zmian.

- [ ] **Step 7: Router** `backend/app/routers/avatars.py`:

```python
"""Awatar użytkownika: upload/usuń własny, podgląd cudzego wg can_see_watcher."""
import pathlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import Viewer as viewer
from ..models import User
from .complaints_common import _looks_like_image
from .forwarding_files import commit_with_file, read_upload_capped
from .watchers import can_see_watcher

router = APIRouter(prefix="/api", tags=["awatar"])

AVATAR_MAX_MB = 2


def avatars_dir() -> pathlib.Path:
    path = pathlib.Path(settings.uploads_dir) / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.post("/me/avatar", status_code=status.HTTP_201_CREATED)
def upload_avatar(file: UploadFile, db: Session = Depends(get_db), user: User = viewer):
    content = read_upload_capped(file, AVATAR_MAX_MB, "Awatar")
    if not _looks_like_image(content[:16]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Dozwolone są tylko obrazy (JPG/PNG/WEBP/GIF).")
    ext = ".png" if content.startswith(b"\x89PNG") else ".jpg"
    stored = f"u{user.id}_{secrets.token_hex(8)}{ext}"
    old = user.avatar
    user.avatar = stored
    commit_with_file(db, avatars_dir() / stored, content)
    if old:
        (avatars_dir() / old).unlink(missing_ok=True)
    return {"has_avatar": True}


@router.delete("/me/avatar")
def delete_avatar(db: Session = Depends(get_db), user: User = viewer):
    old = user.avatar
    user.avatar = ""
    db.commit()
    if old:
        (avatars_dir() / old).unlink(missing_ok=True)
    return {"has_avatar": False}


@router.get("/users/{user_id}/avatar")
def get_avatar(user_id: int, db: Session = Depends(get_db), user: User = viewer):
    target = db.get(User, user_id)
    if target is None or not target.avatar or not can_see_watcher(user, target):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    path = avatars_dir() / target.avatar
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return FileResponse(path, media_type="image/png" if path.suffix == ".png" else "image/jpeg",
                        headers={"Cache-Control": "private, max-age=300"})
```

Sprawdź nazwę modułu konfiguracji (`from ..config import settings` — tak jak w `routers/tracking.py`) i to, że `user` z `Viewer` jest związany z tą samą sesją `db` (jeśli nie — pobierz `db.get(User, user.id)` przed modyfikacją). Jeśli `Viewer` blokuje którąś rolę, a awatar ma mieć każdy zalogowany — użyj zależności „zalogowany" z `deps.py` (tej, którą używa `/api/auth/me`).

- [ ] **Step 8: Rejestracja** — `main.py`: `avatars,` w bloku importów (alfabetycznie) i `app.include_router(avatars.router)` obok `watchers`.

- [ ] **Step 9: Run** `python -m pytest -q tests/test_avatars.py tests/test_watchers.py tests/test_migration_chain.py` → PASS; `python -m alembic heads` → `avatar001 (head)`.

- [ ] **Step 10: Commit** `feat(awatar): upload awatara w profilu, podgląd wg reguły widoczności obserwujących`

---

### Task 2: Obserwujący w danych mapy i statków (bez N+1)

**Files:**
- Modify: `backend/app/routers/watchers.py` (funkcja zbiorcza)
- Modify: `backend/app/routers/tracking.py` (`tracking_map` — pole `watchers` w każdym punkcie; `tracked_vessels` — pole `watchers`)
- Modify: `backend/app/schemas/containers.py` (`TrackedVesselOut.watchers: list[dict] = []`)
- Test: `backend/tests/test_watchers_map.py`

**Interfaces:**
- Consumes: `can_see_watcher` (Task 1).
- Produces: `watchers_by_target(db, model, target_col, target_ids: list[int], user) -> dict[int, list[dict]]`, gdzie dict = `{"user_id", "name", "has_avatar"}` (bez powodu — mapa pokazuje tylko kto); w `/api/tracking/map` każdy element `points`/`unlocated` ma `watchers`; w `/api/tracking/vessels` każdy statek ma `watchers`.

- [ ] **Step 1: Failing test** `backend/tests/test_watchers_map.py`:

```python
"""Obserwujący doklejeni do mapy i listy statków — jednym zapytaniem, wg reguły widoczności."""
from app.models import TrackedVessel
from tests.conftest import login


def _company_id(client, headers, code="ACME"):
    return next(c["id"] for c in client.get("/api/companies", headers=headers).json()
                if c["code"] == code)


def test_vessels_list_has_watchers(client, db_session):
    h = login(client)
    acme = _company_id(client, h)
    client.post("/api/containers", headers=h, json={
        "container_no": "TGBU6784203", "company_id": acme, "vessel": "MV MAPA"})
    v = TrackedVessel(name="MV MAPA", lat=10.0, lon=20.0)
    db_session.add(v)
    db_session.commit()
    client.post(f"/api/tracking/vessels/{v.id}/watch", headers=h, json={"reason": "x"})

    vessels = client.get("/api/tracking/vessels", headers=h).json()
    mine = next(x for x in vessels if x["id"] == v.id)
    assert len(mine["watchers"]) == 1
    assert set(mine["watchers"][0]) == {"user_id", "name", "has_avatar"}


def test_map_points_have_watchers_key(client):
    h = login(client)
    data = client.get("/api/tracking/map", headers=h).json()
    for p in data["points"] + data["unlocated"]:
        assert "watchers" in p
```

(Punkty mapy wymagają kontenera śledzonego — `service.TRACKED` = numer RF + numer kontenera + zdarzenie z lokalizacją. Jeśli łatwo zbudować taki kontener wzorem `backend/tests/test_tracking.py` / `tracking.map` testów, dodaj asercję na konkretnego obserwującego; w przeciwnym razie zostaw test klucza.)

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: `watchers_by_target`** w `routers/watchers.py`:

```python
def watchers_by_target(db: Session, model, target_col, target_ids: list[int],
                       user: User) -> dict[int, list[dict]]:
    """Obserwujący wielu obiektów naraz (mapa, lista statków) — jedno zapytanie, ta sama reguła."""
    if not target_ids:
        return {}
    rows = db.execute(
        select(target_col, User).join(User, User.id == model.user_id)
        .where(target_col.in_(target_ids))
        .order_by(model.created_at.asc().nulls_first(), model.id)).all()
    out: dict[int, list[dict]] = {}
    for target_id, u in rows:
        if can_see_watcher(user, u):
            out.setdefault(target_id, []).append(
                {"user_id": u.id, "name": u.full_name or u.login, "has_avatar": u.has_avatar})
    return out
```

- [ ] **Step 4: Wpięcie** — w `tracking_map` po zbudowaniu `containers`: `watch = watchers_by_target(db, WatchedContainer, WatchedContainer.container_id, ids, user)` i `"watchers": watch.get(c.id, [])` w `entry`. W `tracked_vessels`: `watch = watchers_by_target(db, WatchedVessel, WatchedVessel.vessel_id, [v.id for v in vessels], user)` i `watchers=watch.get(v.id, [])` w `TrackedVesselOut(...)`. Importy lokalnie w funkcjach (`from .watchers import watchers_by_target`), bo `watchers.py` importuje z `tracking.py`. `tracking.py` musi zostać ≤ 500 linii.

- [ ] **Step 5: Run** `python -m pytest -q tests/test_watchers_map.py tests/test_watchers.py tests/test_vessel_card.py tests/test_tracking.py tests/test_query_bounds.py` → PASS.

- [ ] **Step 6: Commit** `feat(mapa): obserwujący kontenerów i statków w danych mapy (jedno zapytanie)`

---

### Task 3: Front — `UserAvatar`, panel profilu, „Śledzone przez…" z awatarem

**Files:**
- Create: `frontend/src/pages/watch/UserAvatar.tsx`
- Create: `frontend/src/pages/profile/AvatarSection.tsx`
- Create: `frontend/src/i18n/features/awatar.ts`
- Modify: `frontend/src/pages/ProfilePage.tsx` (render `<AvatarSection />` nad `<TwoFactorSection />`)
- Modify: `frontend/src/pages/watch/WatchersPanel.tsx` (zamiast `.avatar-initials` → `<UserAvatar …/>`; typ wpisu + `has_avatar`)
- Modify: `frontend/src/types/core.ts` (`User.has_avatar?: boolean`)
- Test: `frontend/src/pages/watch/avatar.dom.test.tsx`

**Interfaces:**
- Consumes: `initials(name)` z `WatchersPanel.tsx` (przenieś do `UserAvatar.tsx` i eksportuj stamtąd; `WatchersPanel` importuje); `useUser()` z `frontend/src/App` (bieżący user); `api.upload/del` z `frontend/src/api.ts`.
- Produces: `export default function UserAvatar({ userId, name, hasAvatar, size = 24, rev }: { userId: number; name: string; hasAvatar: boolean; size?: number; rev?: number })`; `export const initials`; `export const avatarColor = (id: number) => string` (stała paleta 8 kolorów, indeks `id % 8`).

- [ ] **Step 1: Teksty** `frontend/src/i18n/features/awatar.ts`:

```ts
// Awatar użytkownika (profil) — miniatura w „Śledzone przez…" i na mapie
import { defineFeature } from '../feature'

export default defineFeature({
  pl: { avatarTitle: 'Zdjęcie profilowe', avatarChange: 'Zmień zdjęcie', avatarRemove: 'Usuń zdjęcie',
        avatarHint: 'JPG lub PNG, do 2 MB. Widoczne dla zespołu przy obserwowanych kontenerach i statkach.' },
  en: { avatarTitle: 'Profile photo', avatarChange: 'Change photo', avatarRemove: 'Remove photo',
        avatarHint: 'JPG or PNG, up to 2 MB. Shown to the team next to watched containers and vessels.' },
  pt: { avatarTitle: 'Foto de perfil', avatarChange: 'Alterar foto', avatarRemove: 'Remover foto',
        avatarHint: 'JPG ou PNG, até 2 MB. Visível para a equipa junto de contentores e navios observados.' },
})
```

- [ ] **Step 2: Failing test** `frontend/src/pages/watch/avatar.dom.test.tsx`:

```tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import UserAvatar, { avatarColor, initials } from './UserAvatar'

afterEach(cleanup)

describe('UserAvatar', () => {
  it('bez zdjęcia pokazuje inicjały na stałym kolorze', () => {
    render(<UserAvatar userId={5} name="Jan Kowalski" hasAvatar={false} />)
    const el = screen.getByText('JK')
    expect(el.getAttribute('style')).toContain(avatarColor(5))
    expect(initials('ala')).toBe('A')
  })

  it('ze zdjęciem ładuje /api/users/{id}/avatar, a błąd obrazka wraca do inicjałów', () => {
    render(<UserAvatar userId={7} name="Ala Nowak" hasAvatar />)
    const img = screen.getByRole('img', { name: 'Ala Nowak' })
    expect(img.getAttribute('src')).toContain('/api/users/7/avatar')
    fireEvent.error(img)
    expect(screen.getByText('AN')).toBeTruthy()
  })
})
```

- [ ] **Step 3: Run** `npx vitest run src/pages/watch/avatar.dom.test.tsx` → FAIL.

- [ ] **Step 4: `UserAvatar.tsx`**

```tsx
import { useState } from 'react'

const PALETTE = ['#2f6fb2', '#0e8a6a', '#8a5c00', '#7a4fb5', '#b2472f', '#2f8a9e', '#5c6b2f', '#a13d73']
export const avatarColor = (id: number) => PALETTE[Math.abs(id) % PALETTE.length]

export const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]!.toUpperCase()).join('') || '?'

/** Miniatura użytkownika: zdjęcie (GET /api/users/{id}/avatar, cookies) albo inicjały. */
export default function UserAvatar({ userId, name, hasAvatar, size = 24, rev }: {
  userId: number; name: string; hasAvatar: boolean; size?: number; rev?: number
}) {
  const [broken, setBroken] = useState(false)
  const box = { width: size, height: size, fontSize: Math.round(size * 0.42) }
  if (hasAvatar && !broken) {
    return <img className="user-avatar" alt={name} style={box}
                src={`/api/users/${userId}/avatar${rev ? `?r=${rev}` : ''}`}
                onError={() => setBroken(true)} />
  }
  return <span className="user-avatar initials" aria-hidden
               style={{ ...box, background: avatarColor(userId) }}>{initials(name)}</span>
}
```

CSS (do pliku, w którym PR 1 dodał `.avatar-initials` — zastąp tamtą regułę): `.user-avatar { border-radius: 50%; object-fit: cover; flex: none; display: inline-grid; place-items: center; color: #fff; font-weight: 600; }`. Usuń nieużywaną już `.avatar-initials`.

- [ ] **Step 5: `WatchersPanel.tsx`** — usuń lokalne `initials`, importuj `UserAvatar`; w `WatchersResponse.watchers[]` dodaj `has_avatar: boolean`; zamień `<span className="avatar-initials" …>` na `<UserAvatar userId={w.user_id} name={w.name} hasAvatar={w.has_avatar} />`. Zaktualizuj dane w `watch.dom.test.tsx` (dodaj `has_avatar: false` do wpisów; asercja `JK` zostaje).

- [ ] **Step 6: `AvatarSection.tsx`**

```tsx
import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { useUser } from '../../App'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import UserAvatar from '../watch/UserAvatar'

/** Profil: zdjęcie użytkownika (upload / usuń) — miniatura w „Śledzone przez…" i na mapie. */
export default function AvatarSection() {
  const t = useT()
  const user = useUser()
  const { showToast } = useToast()
  const [has, setHas] = useState(Boolean(user?.has_avatar))
  const [rev, setRev] = useState(0)
  if (!user) return null

  const upload = async (file: File | undefined) => {
    if (!file) return
    try {
      await api.upload('/api/me/avatar', file)
      setHas(true); setRev(r => r + 1)
    } catch (e) { showToast(errorMessage(e), 'error') }
  }
  const remove = async () => {
    try { await api.del('/api/me/avatar'); setHas(false) }
    catch (e) { showToast(errorMessage(e), 'error') }
  }
  return (
    <div className="panel">
      <h3>{t('avatarTitle')}</h3>
      <div className="row" style={{ alignItems: 'center', gap: 12 }}>
        <UserAvatar key={rev} userId={user.id} name={user.full_name || user.login}
                    hasAvatar={has} size={64} rev={rev} />
        <label className="btn secondary">
          {t('avatarChange')}
          <input type="file" accept="image/png,image/jpeg,image/webp" hidden
                 onChange={e => { upload(e.target.files?.[0]); e.target.value = '' }} />
        </label>
        {has && <button className="btn secondary" onClick={remove}>{t('avatarRemove')}</button>}
      </div>
      <p className="muted">{t('avatarHint')}</p>
    </div>
  )
}
```

Sprawdź sygnaturę `showToast` w `frontend/src/feedback` (drugi argument — typ komunikatu) i pola `User` w `frontend/src/types/core.ts` (`full_name`, `login`) — dopasuj.

- [ ] **Step 7: `ProfilePage.tsx`** — `import AvatarSection from './profile/AvatarSection'` i `<AvatarSection />` przed `<TwoFactorSection />`.

- [ ] **Step 8: Run** `npx vitest run src/pages/watch src/i18n.features.test.ts` → PASS.

- [ ] **Step 9: Commit** `feat(awatar): zdjęcie w profilu i miniatury w „Śledzone przez…”`

---

### Task 4: Miniatury obserwujących na mapie 2D

**Files:**
- Create: `frontend/src/pages/tracking/AvatarStack.tsx`
- Modify: `frontend/src/pages/tracking/trackingModel.ts` (`MapPoint.watchers`)
- Modify: `frontend/src/pages/tracking/types.ts` (`Vessel.watchers`)
- Modify: `frontend/src/pages/tracking/FlatMap.tsx` (stos przy markerze kontenera i statku)
- Test: `frontend/src/pages/tracking/AvatarStack.dom.test.tsx`

**Interfaces:**
- Consumes: `avatarColor`, `initials` z `frontend/src/pages/watch/UserAvatar.tsx`.
- Produces: `export interface MapWatcher { user_id: number; name: string; has_avatar: boolean }`; `export default function AvatarStack({ watchers, r = 5, idPrefix = "" }: { watchers: MapWatcher[]; r?: number; idPrefix?: string })`, `export function uniqueWatchers(points: { watchers?: MapWatcher[] }[]): MapWatcher[]` — element SVG `<g>` rysowany w lokalnym układzie markera, max 3 kółka + „+n".

- [ ] **Step 1: Failing test** `AvatarStack.dom.test.tsx`:

```tsx
// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import AvatarStack from './AvatarStack'

afterEach(cleanup)

const w = (id: number, has = false) => ({ user_id: id, name: `User ${id}`, has_avatar: has })

it('max 3 miniatury + licznik reszty; zdjęcie przez <image>, inaczej inicjały', () => {
  const { container } = render(<svg><AvatarStack watchers={[w(1, true), w(2), w(3), w(4), w(5)]} /></svg>)
  expect(container.querySelectorAll('.map-avatar')).toHaveLength(3)
  expect(container.querySelector('image')!.getAttribute('href')).toBe('/api/users/1/avatar')
  expect(container.textContent).toContain('+2')
})

it('pusty stos nic nie rysuje', () => {
  const { container } = render(<svg><AvatarStack watchers={[]} /></svg>)
  expect(container.querySelector('.map-avatar')).toBeNull()
})
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: `AvatarStack.tsx`**

```tsx
import { avatarColor, initials } from '../watch/UserAvatar'

export interface MapWatcher { user_id: number; name: string; has_avatar: boolean }

/** Miniatury obserwujących przy markerze mapy (SVG, lokalny układ markera): max 3 + „+n". */
export default function AvatarStack({ watchers, r = 5 }: { watchers: MapWatcher[]; r?: number }) {
  if (watchers.length === 0) return null
  const shown = watchers.slice(0, 3)
  const rest = watchers.length - shown.length
  return (
    <g className="map-avatars" transform={`translate(${r * 1.6},${-r * 1.9})`} pointerEvents="none">
      {shown.map((w, i) => {
        const cx = i * r * 1.4
        const clip = `av-${w.user_id}-${i}`
        return (
          <g key={w.user_id} className="map-avatar">
            <title>{w.name}</title>
            <circle cx={cx} r={r} fill={avatarColor(w.user_id)} stroke="#fff" strokeWidth={r * 0.22} />
            {w.has_avatar ? (
              <>
                <clipPath id={clip}><circle cx={cx} r={r} /></clipPath>
                <image href={`/api/users/${w.user_id}/avatar`} x={cx - r} y={-r}
                       width={r * 2} height={r * 2} clipPath={`url(#${clip})`}
                       preserveAspectRatio="xMidYMid slice" />
              </>
            ) : (
              <text x={cx} y={r * 0.38} textAnchor="middle"
                    style={{ fontSize: r * 1.05, fontWeight: 700, fill: '#fff' }}>{initials(w.name)}</text>
            )}
          </g>
        )
      })}
      {rest > 0 && (
        <text x={shown.length * r * 1.4} y={r * 0.38}
              style={{ fontSize: r * 1.1, fontWeight: 700, fill: '#fff' }}>+{rest}</text>
      )}
    </g>
  )
}
```

(Id `clipPath` musi być unikalne w dokumencie; jeśli ten sam user obserwuje kilka markerów, dodaj do id prefiks markera — przekaż opcjonalny prop `idPrefix: string` i użyj `${idPrefix}-${w.user_id}`.)

- [ ] **Step 4: Typy** — `MapPoint` w `trackingModel.ts`: `watchers?: MapWatcher[]`; `Vessel` w `types.ts`: `watchers?: MapWatcher[]` (import typu z `./AvatarStack`).

- [ ] **Step 5: `FlatMap.tsx`**
  - Marker kontenera (`<g key={key} transform=…>` z `circle r={isActive ? 9 : 7}`): po `<text>` licznika dodaj
    `<AvatarStack idPrefix={`c${key}`} watchers={uniqueWatchers(points)} r={4.5} />`, gdzie `uniqueWatchers` to helper w `AvatarStack.tsx` (eksport): scala `p.watchers ?? []` po `user_id` z zachowaniem kolejności.
  - Marker statku: wewnątrz `<g transform={`translate(${x},${y}) scale(${s * 0.75})`}>` (skala ekranowa) dodaj `<AvatarStack idPrefix={`v${v.id}`} watchers={v.watchers ?? []} r={6} />` — przed `rotate` kursu, żeby stos się nie obracał.
  - `FlatMap.tsx` musi zostać ≤ 500 linii.
  - Dopisz test `uniqueWatchers` w `AvatarStack.dom.test.tsx` (duplikat user_id z dwóch punktów liczony raz).

- [ ] **Step 6: Run** `npx vitest run` (całość) → PASS; `npm run build` → OK; `python scripts/check_file_lengths.py` → rc 0.

- [ ] **Step 7: Commit** `feat(mapa): miniatury obserwujących przy markerach kontenerów i statków`

---

### Task 5: Weryfikacja i PR

- [ ] `cd backend && python -m pytest -q` (pełny) → PASS; `python -m alembic heads` → `avatar001`.
- [ ] `cd frontend && npx vitest run && npm run build` → PASS.
- [ ] Push gałęzi i `gh pr create` — opis: zakres PR 2, testy, uwaga „po Redeploy: katalog `uploads/avatars/` powstaje sam (wolumen uploads)", stopka Generated with Claude Code.
