"""Awizacja: token trzymany jako hash — surowy token działa, baza go nie ujawnia."""
import datetime

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.models import AvizoRequest, Company, Forwarder
from app.routers.avizo import _get_request, _hash_token


def test_avizo_token_stored_hashed_and_lookup_by_raw(client, admin_headers):
    raw = "deadbeef" * 6  # surowy token (jak z linku e-mail)
    with SessionLocal() as db:
        company = db.query(Company).first()
        forwarder = db.query(Forwarder).first()
        avizo = AvizoRequest(
            token=_hash_token(raw), company_id=company.id, forwarder_id=forwarder.id,
            expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=1))
        db.add(avizo)
        db.commit()
        avizo_id = avizo.id
        # w bazie NIE ma surowego tokenu — tylko hash
        assert db.get(AvizoRequest, avizo_id).token != raw
        assert db.get(AvizoRequest, avizo_id).token == _hash_token(raw)

        # lookup po surowym tokenie działa (hashujemy po drodze)
        assert _get_request(db, raw).id == avizo_id
        # błędny token → 404
        with pytest.raises(HTTPException) as exc:
            _get_request(db, "wrong-token")
        assert exc.value.status_code == 404
