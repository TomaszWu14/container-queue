"""Moduł Wiedza (W16): pinezki wiedzy, tematy szkoleniowe, noty eskalacyjne."""
import datetime

from pydantic import BaseModel, Field, field_validator

from ..models import Role
from .base import ORMModel

# --- Moduł Wiedza (W16) ---

KNOWLEDGE_SCOPES = {"screen", "port", "supplier", "customer",
                    "material", "document_type", "process"}


class KnowledgeNoteIn(BaseModel):
    scope_type: str
    scope_key: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    url: str = Field(default="", max_length=500)

    @field_validator("scope_type")
    @classmethod
    def _scope(cls, v: str) -> str:
        if v not in KNOWLEDGE_SCOPES:
            raise ValueError(f"nieznany scope_type: {v}")
        return v


class KnowledgeNoteOut(ORMModel):
    id: int
    scope_type: str
    scope_key: str
    title: str
    body: str
    url: str
    is_active: bool
    created_at: datetime.datetime
    created_by_name: str = ""
    created_by_id: int | None = None   # ACL-001: edycja tylko autor/admin


class TrainingTopicIn(BaseModel):
    scope_type: str = ""
    scope_key: str = ""
    title: str = Field(min_length=1, max_length=200)
    body: str = ""


class TrainingTopicOut(ORMModel):
    id: int
    scope_type: str
    scope_key: str
    title: str
    body: str
    status: str
    created_at: datetime.datetime
    created_by_name: str = ""
    votes: int = 0
    my_vote: bool = False


class BulletinIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    roles: list[str] = Field(min_length=1)
    # tylko konta grupowe (admin / view_all) wybierają spółkę; NULL = cała grupa.
    # Logistyk jednej spółki zawsze adresuje swoją spółkę (pole ignorowane).
    company_id: int | None = None

    @field_validator("roles")
    @classmethod
    def _roles(cls, v: list[str]) -> list[str]:
        valid = {r.value for r in Role}
        bad = [r for r in v if r not in valid]
        if bad:
            raise ValueError(f"nieznane role: {', '.join(bad)}")
        return v


class BulletinOut(ORMModel):
    id: int
    title: str
    body: str
    roles: list[str]
    company_id: int | None = None
    created_at: datetime.datetime
    created_by_name: str = ""


class BulletinAckOut(BaseModel):
    user_id: int
    login: str
    full_name: str
    role: str
    read_at: datetime.datetime | None = None
