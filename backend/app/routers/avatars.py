"""Awatar użytkownika: upload/usuń własny, podgląd cudzego wg can_see_watcher."""
import pathlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import Viewer as viewer
from ..deps import ViewerOrSales as viewer_or_sales
from ..models import User
from .forwarding_files import commit_with_file, read_upload_capped
from .watchers import can_see_watcher

router = APIRouter(prefix="/api", tags=["awatar"])

AVATAR_MAX_MB = 2

# Sygnatura -> (rozszerzenie, media type). HEIC nie ma tu wpisu - odrzucamy (przeglądarki go nie wyświetlą).
_AVATAR_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\xff\xd8\xff", ".jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", ".png", "image/png"),
    (b"GIF87a", ".gif", "image/gif"),
    (b"GIF89a", ".gif", "image/gif"),
]
_AVATAR_MEDIA_TYPES = {ext: media for _, ext, media in _AVATAR_SIGNATURES}
_AVATAR_MEDIA_TYPES[".webp"] = "image/webp"


def _avatar_kind(head: bytes) -> tuple[str, str] | None:
    """Rozpoznaje typ awatara po sygnaturze bajtowej i zwraca (rozszerzenie, media type)."""
    for sig, ext, media in _AVATAR_SIGNATURES:
        if head.startswith(sig):
            return ext, media
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return None


def avatars_dir() -> pathlib.Path:
    path = pathlib.Path(settings.uploads_dir) / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.post("/me/avatar", status_code=status.HTTP_201_CREATED)
def upload_avatar(file: UploadFile, db: Session = Depends(get_db), user: User = viewer):
    content = read_upload_capped(file, AVATAR_MAX_MB, "Awatar")
    kind = _avatar_kind(content[:16])
    if kind is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Dozwolone są tylko obrazy JPG/PNG/WEBP/GIF.")
    ext, _ = kind
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
def get_avatar(user_id: int, db: Session = Depends(get_db), user: User = viewer_or_sales):
    target = db.get(User, user_id)
    if target is None or not target.avatar or not can_see_watcher(user, target):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    path = avatars_dir() / target.avatar
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    media_type = _AVATAR_MEDIA_TYPES.get(path.suffix, "application/octet-stream")
    return FileResponse(path, media_type=media_type,
                        headers={"Cache-Control": "private, no-cache"})
