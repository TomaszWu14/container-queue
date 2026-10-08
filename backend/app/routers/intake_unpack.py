"""Poczekalnia — rozpakowanie wejścia przed cięciem (spec 2026-10-06-dokumenty-dostaw, decyzje 8 i 19):
ZIP jak dotąd, .eml/.msg jak ZIP (załączniki idą dalej tą samą ścieżką, sama wiadomość zostaje jako
korespondencja — typ MAIL), zdjęcia JPG/PNG/HEIC → jednostronicowy PDF (dalej jak skan, bez OCR)."""
import email
import io
import pathlib
from collections.abc import Iterator
from email import policy
from email.message import EmailMessage

from fastapi import HTTPException, status

from ..config import settings
from .archive_upload import MAX_UNCOMPRESSED_MB, unpack
from .forwarding_files import allowed_extensions, safe_filename

MAIL_EXTS = ("eml", "msg")
IMAGE_EXTS = ("jpg", "jpeg", "png", "heic", "heif")
INTAKE_EXTRA_EXTS = {"heic", "heif"}   # tylko poczekalnia — zwykły upload załączników bez zmian
MAX_DEPTH = 3
INLINE_LOGO_BYTES = 20 * 1024


class _TooLarge(HTTPException):
    """Przekroczony budżet całego wgrania — przerywa wgranie (nie pomija po cichu reszty)."""

    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail)


class _Budget:
    """Suma plików i bajtów po rozpakowaniu całego wgrania (anty-bomba jak w archive_upload)."""

    def __init__(self) -> None:
        self.count = self.size = 0

    def take(self, data: bytes) -> None:
        self.count += 1
        self.size += len(data)
        if self.count > settings.archive_zip_max_files:
            raise _TooLarge(f"Wgranie ma po rozpakowaniu ponad {settings.archive_zip_max_files} plików.")
        if self.size > MAX_UNCOMPRESSED_MB * 1024 * 1024:
            raise _TooLarge(f"Wgranie po rozpakowaniu przekracza {MAX_UNCOMPRESSED_MB} MB.")


def expand(files: list[tuple[str, bytes]]) -> tuple[list[tuple[str, bytes]], list[str]]:
    """[(nazwa, bajty)] → (pliki do cięcia, pominięte z powodem). Maile zostają na liście (MAIL)."""
    entries: list[tuple[str, bytes]] = []
    skipped: list[str] = []
    _expand(files, 0, _Budget(), entries, skipped)
    return entries, skipped


def _expand(files: list[tuple[str, bytes]], depth: int, budget: _Budget,
            entries: list[tuple[str, bytes]], skipped: list[str]) -> None:
    allowed = allowed_extensions() | INTAKE_EXTRA_EXTS
    for raw_name, data in files:
        name = safe_filename(raw_name)
        ext = pathlib.PurePath(name).suffix.lower().lstrip(".")
        if ext in ("zip", *MAIL_EXTS) and depth >= MAX_DEPTH:
            skipped.append(f"{name} (zbyt głębokie zagnieżdżenie)")
            continue
        try:
            if ext == "zip":
                _, inner, inner_skipped = unpack(data)
                skipped += inner_skipped
                _expand(inner, depth + 1, budget, entries, skipped)
            elif ext in MAIL_EXTS:
                inner = list(_eml_parts(data, skipped) if ext == "eml" else _msg_parts(data, skipped))
                budget.take(data)
                entries.append((name, data))   # korespondencja — oryginał wiadomości
                _expand(inner, depth + 1, budget, entries, skipped)
            elif ext in IMAGE_EXTS:
                pdf = image_to_pdf(data)
                budget.take(pdf)
                entries.append((f"{pathlib.PurePath(name).stem}.pdf", pdf))
            elif ext in allowed:
                budget.take(data)
                entries.append((name, data))
            else:
                skipped.append(f"{name} (niedozwolony typ)")
        except _TooLarge:
            raise
        except HTTPException as exc:
            skipped.append(f"{name} ({exc.detail})")   # zły ZIP/mail/obraz pomija TEN plik


def _is_logo(inline: bool, size: int) -> bool:
    return inline and size < INLINE_LOGO_BYTES


def _eml_parts(data: bytes, skipped: list[str]) -> Iterator[tuple[str, bytes]]:
    msg = email.message_from_bytes(data, policy=policy.default)
    if not isinstance(msg, EmailMessage) or not msg.keys():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nie udało się odczytać wiadomości")
    for part in _leaves(msg):
        if (part.get_content_maintype() == "text" and not part.get_filename()
                and part.get_content_disposition() != "attachment"):
            continue   # treść wiadomości — zostaje w oryginale .eml
        if part.get_content_type() == "message/rfc822":
            inner = part.get_content()
            subject = str(inner.get("subject") or "wiadomosc")
            name = part.get_filename() or subject
            yield (name if name.lower().endswith(".eml") else f"{name}.eml"), inner.as_bytes()
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        name = part.get_filename() or f"zalacznik.{part.get_content_subtype()}"
        if _is_logo(part.get_content_disposition() == "inline", len(payload)):
            skipped.append(f"{name} (obraz w treści maila)")
            continue
        yield name, payload


def _leaves(part: EmailMessage) -> Iterator[EmailMessage]:
    """Liście drzewa MIME (także obrazy w multipart/related); załączony mail to liść, nie gałąź."""
    for sub in part.iter_parts():
        if isinstance(sub, EmailMessage):
            if sub.is_multipart() and sub.get_content_type() != "message/rfc822":
                yield from _leaves(sub)
            else:
                yield sub


def _msg_parts(data: bytes, skipped: list[str]) -> Iterator[tuple[str, bytes]]:
    import extract_msg   # leniwie — ciężka paczka, potrzebna tylko przy .msg

    try:
        msg = extract_msg.openMsg(data)
    except Exception as exc:   # olefile/extract_msg rzucają różne wyjątki dla złych plików
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "nie udało się odczytać wiadomości Outlooka") from exc
    try:
        yield from _msg_attachments(msg, skipped)
    finally:
        msg.close()


def _msg_attachments(msg, skipped: list[str]) -> Iterator[tuple[str, bytes]]:
    for att in msg.attachments:
        name = att.longFilename or att.shortFilename or att.displayName or "zalacznik"
        payload = att.data
        if hasattr(payload, "attachments"):
            # ponytail: zagnieżdżony .msg bez bajtów oryginału — wchodzą tylko jego załączniki
            yield from _msg_attachments(payload, skipped)
            continue
        if not isinstance(payload, bytes):
            continue
        if _is_logo(bool(att.hidden or att.contentId), len(payload)):
            skipped.append(f"{name} (obraz w treści maila)")
            continue
        yield name, payload


def image_to_pdf(data: bytes) -> bytes:
    """Zdjęcie (JPG/PNG/HEIC) → jednostronicowy PDF; orientacja z EXIF, kolory RGB."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    from pillow_heif import register_heif_opener

    register_heif_opener()
    try:
        with Image.open(io.BytesIO(data)) as img:
            page = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nieczytelny obraz") from exc
    buf = io.BytesIO()
    page.save(buf, format="PDF", resolution=150)
    return buf.getvalue()
