"""Reklamacje — pisma: treść e-maila do spedycji/ubezpieczyciela i drukowalny
szablon pisma (W11 #70, PL/EN)."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import Viewer as viewer
from ..html_templates import render
from ..models import Complaint, User
from ..print_button import PRINT_SCRIPT
from .containers_common import hidden_fields
from .complaints_common import (
    COST_ROLES,
    _problem_lines,
    _timeline_lines,
    complaint_deadline,
    get_complaint_checked,
)

# podpinany w routers/complaints.py (router.include_router) — main.py bez zmian
router = APIRouter()   # prefiks /api i tag dziedziczy z routera nadrzędnego


def _complaint_email_html(complaint: Complaint, message: str) -> str:
    container = complaint.container
    return render("complaints/email.html", number=complaint.number,
                  container_no=container.container_no if container else "",
                  problems=_problem_lines(complaint), description=complaint.description,
                  photos=len(complaint.photos), message=message)


# --- szablon pisma (W11 #70) ---
# Świadomie HTML print-view (CSS @media print), nie „prawdziwy" PDF: repo nie ma
# biblioteki generującej PDF (pdfminer/pdfplumber tylko czytają), a przeglądarka
# drukuje ten widok do PDF bez żadnej nowej zależności.

_LETTER_L10N = {
    "pl": {"title": "Reklamacja", "container": "Kontener", "problems": "Problemy",
           "desc": "Opis", "claim": "Kwota roszczenia", "created": "Data utworzenia",
           "deadline": "Termin przedawnienia", "timeline": "Oś czasu dostawy",
           "photos": "Zdjęcia dowodowe (w systemie)", "greeting": "Dzień dobry,",
           "intro": "niniejszym zgłaszamy reklamację dotyczącą dostawy kontenera",
           "outro": "Prosimy o odniesienie się do reklamacji w terminie i wyjaśnienie sprawy.",
           "sign": "Z poważaniem,\nDział Logistyki", "to": "Adresat",
           "vessel": "Statek", "eta": "ETA", "supplier": "Dostawca"},
    "en": {"title": "Claim", "container": "Container", "problems": "Issues",
           "desc": "Description", "claim": "Claim amount", "created": "Created on",
           "deadline": "Limitation deadline", "timeline": "Delivery timeline",
           "photos": "Evidence photos (available in system)", "greeting": "Dear Sirs,",
           "intro": "we hereby submit a claim regarding the delivery of container",
           "outro": "Please respond to this claim in due time and clarify the matter.",
           "sign": "Kind regards,\nLogistics Department", "to": "Addressee",
           "vessel": "Vessel", "eta": "ETA", "supplier": "Supplier"},
}

_RECIPIENT_LABELS = {
    "PRZEWOZNIK": {"pl": "Przewoźnik", "en": "Carrier"},
    "UBEZPIECZYCIEL": {"pl": "Ubezpieczyciel", "en": "Insurer"},
    "DOSTAWCA": {"pl": "Dostawca", "en": "Supplier"},
}


@router.get("/complaints/{complaint_id}/letter", response_class=HTMLResponse)
def complaint_letter(complaint_id: int, lang: str = Query(default="pl"),
                     db: Session = Depends(get_db), user: User = viewer):
    complaint = get_complaint_checked(db, complaint_id, user)
    L = _LETTER_L10N.get(lang, _LETTER_L10N["pl"])
    lang = lang if lang in _LETTER_L10N else "pl"
    container = complaint.container
    recipient = _RECIPIENT_LABELS.get(complaint.recipient_type, {}).get(lang, "")
    deadline = complaint_deadline(complaint)
    hidden = hidden_fields(user)
    rows = [
        (L["container"], container.container_no),
        (L["supplier"], container.supplier.name
         if container.supplier and "supplier_name" not in hidden else ""),
        (L["vessel"], container.vessel),
        (L["eta"], container.eta),
        (L["problems"], _problem_lines(complaint)),
        (L["created"], complaint.created_at.date()),
        (L["claim"], f"{complaint.claim_amount} {complaint.claim_currency}"
         if complaint.claim_amount is not None and user.role in COST_ROLES else ""),
        (L["deadline"], deadline or ""),
        (L["to"], " · ".join(x for x in (recipient, complaint.sent_target) if x)),
        (L["photos"], len(complaint.photos) or ""),
    ]
    return HTMLResponse(render(
        "complaints/letter.html", lang=lang, L=L, number=complaint.number,
        container_no=container.container_no, rows=[(k, v) for k, v in rows if v],
        description=complaint.description, timeline=_timeline_lines(db, container, hide_orders="order_number" in hidden),
        print_script=PRINT_SCRIPT))
