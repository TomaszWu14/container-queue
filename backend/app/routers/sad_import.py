"""Import podglądów SAD z WinSAD (PDF): sprawdzenie zgłoszeń i raport Excel. Pliki czytane
w pamięci (bez zapisu na dysk). Uprawnienia jak drafty SAD (PurchasingReaders); zakres spółek
i ślad audytu — app/sad_import/service.py (reguła izolacji: deps.check_container_access)."""
import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import PurchasingReaders as sad_readers
from ..models import User
from ..sad_import import service
from ..sad_import.excel import build_workbook
from .forwarding_files import read_upload_capped, safe_filename

router = APIRouter(prefix="/api/sad-import", tags=["import SAD"])

MAX_FILES = 20
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _read(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Wybierz pliki PDF z WinSAD.")
    if len(files) > MAX_FILES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Naraz można sprawdzić najwyżej {MAX_FILES} plików.")
    return [(safe_filename(f.filename, "SAD.pdf"),
             read_upload_capped(f, settings.max_upload_mb, "SAD")) for f in files]


@router.post("/check")
def check_sad(files: list[UploadFile] = File(...), db: Session = Depends(get_db),
              user: User = sad_readers) -> dict:
    results = service.check_files(db, user, _read(files))
    return {"files": [service.to_json(r) for r in results]}


@router.post("/report")
def sad_report(files: list[UploadFile] = File(...), db: Session = Depends(get_db),
               user: User = sad_readers) -> Response:
    results = service.check_files(db, user, _read(files), note="Import SAD: raport Excel")
    parsed = [(r.zgloszenie, r.wyniki) for r in results if r.ok and r.zgloszenie is not None]
    if not parsed:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Żaden plik nie jest dostępnym dla Ciebie podglądem SAD z WinSAD.")
    workbook = build_workbook([z for z, _ in parsed], [w for _, w in parsed])
    filename = f"sad_raport_{datetime.date.today().isoformat()}.xlsx"
    return Response(workbook.getvalue(), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
